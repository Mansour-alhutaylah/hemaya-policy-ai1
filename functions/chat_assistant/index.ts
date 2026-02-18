import { createClientFromRequest } from "npm:@base44/sdk";

interface ChatRequest {
  message: string;
  policy_id?: string;
}

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { message, policy_id }: ChatRequest = await req.json();

    if (!message) {
      return Response.json({ error: "message is required" }, { status: 400 });
    }

    const lowerMessage = message.toLowerCase();

    // Get context data
    const policies = await base44.entities.Policy.list();
    const results = await base44.entities.ComplianceResult.list();
    const gaps = await base44.entities.Gap.list();

    let response = "";

    // Policy questions
    if (lowerMessage.includes("policy") || lowerMessage.includes("policies")) {
      if (policies.length === 0) {
        response = "You haven't uploaded any policies yet. Go to the Policies page to upload your first security policy document.";
      } else {
        const policyNames = policies.slice(0, 5).map(p => p.file_name).join(", ");
        response = `You have ${policies.length} policies uploaded: ${policyNames}${policies.length > 5 ? ", ..." : ""}.\n\nI can help you:\n- Analyze compliance status\n- Identify gaps\n- Suggest improvements`;
      }
    }
    // Gap questions
    else if (lowerMessage.includes("gap") || lowerMessage.includes("missing")) {
      const openGaps = gaps.filter(g => g.status === "Open");
      const criticalGaps = gaps.filter(g => g.severity === "Critical");

      if (openGaps.length === 0) {
        response = "Excellent! You have no open compliance gaps. Your security posture is strong.";
      } else {
        response = `You have **${openGaps.length} open gaps**${criticalGaps.length > 0 ? `, including ${criticalGaps.length} critical` : ""}.\n\n**Recommendations:**\n1. Address critical gaps first\n2. Assign owners to unassigned gaps\n3. Set realistic remediation timelines`;
      }
    }
    // Score questions
    else if (lowerMessage.includes("score") || lowerMessage.includes("compliance")) {
      if (results.length === 0) {
        response = "No compliance analyses have been run yet. Upload a policy and run an analysis to see your scores.";
      } else {
        const latestByFramework: Record<string, any> = {};
        results.forEach(r => {
          if (!latestByFramework[r.framework] || 
              new Date(r.analyzed_at) > new Date(latestByFramework[r.framework].analyzed_at)) {
            latestByFramework[r.framework] = r;
          }
        });

        const summaries = Object.values(latestByFramework)
          .map(r => `- **${r.framework}**: ${Math.round(r.compliance_score || 0)}%`)
          .join("\n");

        response = `**Current Compliance Status:**\n\n${summaries}\n\n**Insight:** Focus on frameworks below 70% for the biggest impact.`;
      }
    }
    // Framework-specific
    else if (lowerMessage.includes("nca") || lowerMessage.includes("ecc")) {
      response = "**NCA ECC** is Saudi Arabia's national cybersecurity framework with 5 key domains:\n\n1. Cybersecurity Governance\n2. Cybersecurity Defense\n3. Cybersecurity Resilience\n4. Third-Party Cybersecurity\n5. ICS Cybersecurity\n\nTo improve compliance, focus on risk assessment, security baselines, and incident response.";
    }
    else if (lowerMessage.includes("iso") || lowerMessage.includes("27001")) {
      response = "**ISO 27001:2022** is the international ISMS standard with 93 controls across 4 domains:\n\n- Organizational (A.5)\n- People (A.6)\n- Physical (A.7)\n- Technological (A.8)\n\nKey requirements: ISMS scope, risk assessment, Statement of Applicability, and internal audits.";
    }
    else if (lowerMessage.includes("nist") || lowerMessage.includes("800-53")) {
      response = "**NIST 800-53** provides 1000+ security controls for federal systems across 20 families:\n\nAC (Access Control), AU (Audit), CA (Assessment), CM (Configuration), IR (Incident Response), and more.\n\nImplementation: Categorize systems → Select baseline → Implement → Assess → Authorize → Monitor.";
    }
    // Help
    else if (lowerMessage.includes("help") || lowerMessage.includes("what can")) {
      response = "I'm your AI Compliance Assistant! I can help with:\n\n📊 **Analysis**\n- Compliance scores\n- Gap identification\n- Risk prioritization\n\n📚 **Frameworks**\n- NCA ECC, ISO 27001, NIST 800-53\n- Control requirements\n- Best practices\n\n📝 **Guidance**\n- Policy improvements\n- Remediation strategies\n\nJust ask me anything!";
    }
    // Default
    else {
      response = `I can help you with:\n- **Compliance status** - Current scores and trends\n- **Gap analysis** - Identifying missing controls\n- **Frameworks** - NCA ECC, ISO 27001, NIST requirements\n- **Improvements** - Suggestions to enhance compliance\n\nWhat would you like to know?`;
    }

    return Response.json({
      response,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Chat error:", error);
    return Response.json({ 
      error: error.message || "Chat failed" 
    }, { status: 500 });
  }
});