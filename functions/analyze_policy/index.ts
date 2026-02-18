import { createClientFromRequest } from "npm:@base44/sdk";

interface AnalyzeRequest {
  policy_id: string;
  frameworks: string[];
}

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { policy_id, frameworks }: AnalyzeRequest = await req.json();

    if (!policy_id || !frameworks || frameworks.length === 0) {
      return Response.json({ error: "policy_id and frameworks are required" }, { status: 400 });
    }

    // Get policy
    const policy = await base44.entities.Policy.get(policy_id);
    if (!policy) {
      return Response.json({ error: "Policy not found" }, { status: 404 });
    }

    // Update policy status to processing
    await base44.asServiceRole.entities.Policy.update(policy_id, { status: "processing" });

    // Extract text if needed
    let extractedText = policy.content_preview || "";
    if (!extractedText && policy.file_url) {
      try {
        // Try to extract text from file
        const extractResult = await base44.integrations.Core.ExtractDataFromUploadedFile({
          file_url: policy.file_url,
          json_schema: {
            type: "object",
            properties: {
              text: { type: "string" }
            }
          }
        });
        
        if (extractResult.status === "success" && extractResult.output?.text) {
          extractedText = extractResult.output.text;
        }
      } catch (e) {
        console.error("Text extraction failed:", e);
      }
    }

    if (!extractedText) {
      await base44.asServiceRole.entities.Policy.update(policy_id, { 
        status: "failed" 
      });
      return Response.json({ error: "Could not extract text from policy" }, { status: 400 });
    }

    // Normalize text for matching
    const policyText = extractedText.toLowerCase();
    const policyWords = new Set(policyText.split(/\s+/));

    // Process each framework
    const results = [];
    const allMappings = [];
    const allGaps = [];

    for (const framework of frameworks) {
      // Get controls for this framework
      const controls = await base44.asServiceRole.entities.ControlLibrary.filter({ framework });

      let controlsCovered = 0;
      let controlsPartial = 0;
      let controlsMissing = 0;

      // Match controls against policy text
      for (const control of controls) {
        const keywords = control.keywords || [];
        let matchCount = 0;

        // Count keyword matches
        for (const keyword of keywords) {
          const keywordLower = keyword.toLowerCase();
          if (policyText.includes(keywordLower)) {
            matchCount++;
          }
        }

        // Calculate confidence score
        const confidence = keywords.length > 0 ? matchCount / keywords.length : 0;

        // Find evidence snippet
        let evidenceSnippet = "";
        if (matchCount > 0) {
          const sentences = extractedText.split(/[.!?]+/);
          for (const sentence of sentences) {
            if (keywords.some(kw => sentence.toLowerCase().includes(kw.toLowerCase()))) {
              evidenceSnippet = sentence.trim();
              break;
            }
          }
        }

        // Categorize control coverage
        if (confidence >= 0.7) {
          controlsCovered++;
        } else if (confidence >= 0.3) {
          controlsPartial++;
        } else {
          controlsMissing++;
          
          // Create gap for missing/partial controls
          allGaps.push({
            policy_id,
            framework,
            control_id: control.control_code,
            control_name: control.title,
            severity: control.severity_if_missing || "Medium",
            status: "Open",
            description: `Control ${control.control_code} not adequately covered in policy`,
          });
        }

        // Create mapping
        allMappings.push({
          policy_id,
          control_id: control.control_code,
          framework,
          evidence_snippet: evidenceSnippet || "No clear evidence found",
          confidence_score: confidence,
          ai_rationale: confidence >= 0.7 
            ? `Strong match found with ${matchCount}/${keywords.length} keywords matched`
            : confidence >= 0.3
            ? `Partial match found with ${matchCount}/${keywords.length} keywords matched`
            : `Weak or no match found with ${matchCount}/${keywords.length} keywords matched`,
          decision: confidence >= 0.6 ? "Accepted" : "Pending",
        });
      }

      // Calculate compliance score
      const totalControls = controls.length;
      const complianceScore = totalControls > 0
        ? ((controlsCovered + controlsPartial * 0.5) / totalControls) * 100
        : 0;

      // Determine status
      let status = "Not Compliant";
      if (complianceScore >= 80) status = "Compliant";
      else if (complianceScore >= 60) status = "Partially Compliant";

      // Create result
      const result = await base44.asServiceRole.entities.ComplianceResult.create({
        policy_id,
        framework,
        compliance_score: complianceScore,
        controls_covered: controlsCovered,
        controls_partial: controlsPartial,
        controls_missing: controlsMissing,
        status,
        analyzed_at: new Date().toISOString(),
        analysis_duration: 0,
      });

      results.push(result);
    }

    // Bulk create mappings and gaps
    if (allMappings.length > 0) {
      await base44.asServiceRole.entities.MappingReview.bulkCreate(allMappings);
    }
    if (allGaps.length > 0) {
      await base44.asServiceRole.entities.Gap.bulkCreate(allGaps);
    }

    // Create AI insights
    const criticalGaps = allGaps.filter(g => g.severity === "Critical");
    if (criticalGaps.length > 0) {
      await base44.asServiceRole.entities.AIInsight.create({
        policy_id,
        insight_type: "gap_priority",
        title: `${criticalGaps.length} Critical Gaps Require Immediate Attention`,
        description: `Analysis identified ${criticalGaps.length} critical compliance gaps that should be addressed urgently.`,
        priority: "Critical",
        confidence: 0.95,
        status: "New",
      });
    }

    // Update policy status
    await base44.asServiceRole.entities.Policy.update(policy_id, { 
      status: "analyzed",
      last_analyzed_at: new Date().toISOString(),
    });

    // Log audit
    await base44.asServiceRole.entities.AuditLog.create({
      actor: user.email,
      action: "analysis_complete",
      target_type: "policy",
      target_id: policy_id,
      details: `Completed analysis across ${frameworks.length} frameworks`,
    });

    return Response.json({
      success: true,
      results,
      mappings_created: allMappings.length,
      gaps_created: allGaps.length,
    });

  } catch (error) {
    console.error("Analysis error:", error);
    return Response.json({ 
      error: error.message || "Analysis failed" 
    }, { status: 500 });
  }
});