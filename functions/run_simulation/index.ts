import { createClientFromRequest } from "npm:@base44/sdk";

interface SimulationRequest {
  policy_id: string;
  control_ids: string[];
}

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { policy_id, control_ids }: SimulationRequest = await req.json();

    if (!policy_id || !control_ids) {
      return Response.json({ error: "policy_id and control_ids are required" }, { status: 400 });
    }

    // Get current compliance results
    const results = await base44.entities.ComplianceResult.filter({ policy_id });
    
    // Get controls being implemented
    const controls = await base44.asServiceRole.entities.ControlLibrary.list();
    const selectedControls = controls.filter(c => control_ids.includes(c.id));

    // Calculate impact by framework
    const impactByFramework: Record<string, number> = {};
    
    selectedControls.forEach(control => {
      if (!impactByFramework[control.framework]) {
        impactByFramework[control.framework] = 0;
      }
      // Each control adds ~1.5% to compliance score
      impactByFramework[control.framework] += 1.5;
    });

    // Calculate projected scores
    const projectedResults = results.map(result => {
      const impact = impactByFramework[result.framework] || 0;
      const currentScore = result.compliance_score || 0;
      const projectedScore = Math.min(100, currentScore + impact);

      return {
        framework: result.framework,
        current_score: Math.round(currentScore),
        projected_score: Math.round(projectedScore),
        improvement: Math.round(projectedScore - currentScore),
        controls_covered: result.controls_covered,
        controls_missing: Math.max(0, result.controls_missing - selectedControls.filter(c => c.framework === result.framework).length),
      };
    });

    // Calculate gaps that would be resolved
    const gaps = await base44.entities.Gap.filter({ policy_id });
    const gapsResolved = gaps.filter(gap => 
      selectedControls.some(c => c.control_code === gap.control_id)
    ).length;

    return Response.json({
      success: true,
      current_results: results.map(r => ({
        framework: r.framework,
        score: Math.round(r.compliance_score || 0),
      })),
      projected_results: projectedResults,
      controls_implemented: control_ids.length,
      gaps_resolved: gapsResolved,
      total_impact: Math.round(
        Object.values(impactByFramework).reduce((a, b) => a + b, 0) / Object.keys(impactByFramework).length
      ),
    });

  } catch (error) {
    console.error("Simulation error:", error);
    return Response.json({ 
      error: error.message || "Simulation failed" 
    }, { status: 500 });
  }
});