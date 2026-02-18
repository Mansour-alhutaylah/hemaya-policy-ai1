import { createClientFromRequest } from "npm:@base44/sdk";

interface ReportRequest {
  policy_id: string;
  report_type: string;
  format: string;
  frameworks_included: string[];
}

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { policy_id, report_type, format, frameworks_included }: ReportRequest = await req.json();

    if (!policy_id) {
      return Response.json({ error: "policy_id is required" }, { status: 400 });
    }

    // Get policy
    const policy = await base44.entities.Policy.get(policy_id);
    if (!policy) {
      return Response.json({ error: "Policy not found" }, { status: 404 });
    }

    // Get compliance results
    const results = await base44.asServiceRole.entities.ComplianceResult.filter({ policy_id });
    const filteredResults = frameworks_included?.length > 0
      ? results.filter(r => frameworks_included.includes(r.framework))
      : results;

    // Get gaps
    const gaps = await base44.asServiceRole.entities.Gap.filter({ policy_id });
    const openGaps = gaps.filter(g => g.status === "Open");

    // Generate report content
    let reportContent = "";
    
    if (report_type === "Executive Summary") {
      reportContent = `
# Compliance Analysis Report
**Policy:** ${policy.file_name}
**Generated:** ${new Date().toISOString()}

## Executive Summary
This report provides an overview of compliance analysis results across ${filteredResults.length} framework(s).

## Compliance Scores
${filteredResults.map(r => `
### ${r.framework}
- **Score:** ${Math.round(r.compliance_score || 0)}%
- **Status:** ${r.status}
- **Controls Covered:** ${r.controls_covered}
- **Controls Partial:** ${r.controls_partial}
- **Controls Missing:** ${r.controls_missing}
`).join('\n')}

## Open Gaps
Total: ${openGaps.length}
${openGaps.slice(0, 10).map(g => `
- **${g.control_id}** (${g.severity}): ${g.control_name}
`).join('\n')}

${openGaps.length > 10 ? `\n... and ${openGaps.length - 10} more gaps` : ''}
`;
    } else if (report_type === "Gap Report") {
      reportContent = `
# Gap Analysis Report
**Policy:** ${policy.file_name}
**Generated:** ${new Date().toISOString()}

## Summary
- Total Gaps: ${gaps.length}
- Open: ${gaps.filter(g => g.status === "Open").length}
- In Progress: ${gaps.filter(g => g.status === "In Progress").length}
- Resolved: ${gaps.filter(g => g.status === "Resolved").length}

## Gaps by Severity
- Critical: ${gaps.filter(g => g.severity === "Critical").length}
- High: ${gaps.filter(g => g.severity === "High").length}
- Medium: ${gaps.filter(g => g.severity === "Medium").length}
- Low: ${gaps.filter(g => g.severity === "Low").length}

## Gap Details
${gaps.map(g => `
### ${g.control_id} - ${g.control_name}
- **Framework:** ${g.framework}
- **Severity:** ${g.severity}
- **Status:** ${g.status}
- **Owner:** ${g.owner || "Unassigned"}
- **Description:** ${g.description}
`).join('\n')}
`;
    } else {
      reportContent = `
# Detailed Compliance Analysis
**Policy:** ${policy.file_name}

Complete analysis results across all frameworks with detailed control mappings.
`;
    }

    // For demo purposes, create a simple text file
    // In production, use a PDF/Excel generation library
    const reportData = format === "PDF" 
      ? reportContent 
      : reportContent;

    // Upload as file
    const blob = new Blob([reportData], { type: 'text/plain' });
    const file = new File([blob], `report_${policy_id}_${Date.now()}.txt`);
    
    const { file_url } = await base44.integrations.Core.UploadFile({ file });

    // Create report record
    const report = await base44.asServiceRole.entities.Report.create({
      policy_id,
      report_type,
      format,
      status: "Completed",
      download_url: file_url,
      frameworks_included,
      generated_at: new Date().toISOString(),
    });

    // Log audit
    await base44.asServiceRole.entities.AuditLog.create({
      actor: user.email,
      action: "report_generate",
      target_type: "report",
      target_id: report.id,
      details: `Generated ${report_type} report in ${format} format`,
    });

    return Response.json({
      success: true,
      report,
    });

  } catch (error) {
    console.error("Report generation error:", error);
    return Response.json({ 
      error: error.message || "Report generation failed" 
    }, { status: 500 });
  }
});