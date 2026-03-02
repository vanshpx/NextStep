/**
 * NexStep Travel Execution Re-Optimization Engine
 * 
 * This service handles intelligent itinerary re-optimization after disruptions.
 * It uses AI to reschedule, replace, or skip activities while maintaining trip integrity.
 */

interface Activity {
    id?: number;
    title: string;
    startTime: string;
    endTime: string;
    locationName: string;
    latitude?: number;
    longitude?: number;
    reason?: string;
}

interface ReoptimizationRequest {
    currentTime: string;
    latitude: number;
    longitude: number;
    tripTheme: string;
    tripEndDate: string;
    completedActivities: Activity[];
    currentActivity: Activity;
    remainingActivities: Activity[];
    issueType: string;
    description: string;
}

interface ReoptimizationResponse {
    actionTaken: 'rescheduled' | 'replaced' | 'skipped' | 'escalated';
    confidenceScore: number;
    updatedActivities: Activity[];
    explanation: string;
}

const SYSTEM_PROMPT = `SYSTEM ROLE
You are NexStep's Travel Execution Re-Optimization Engine.
You operate inside a live B2B travel execution platform.
Your responsibility is to intelligently adjust only the remaining portion of a travel itinerary after a disruption, while preserving system integrity and travel intent.
You are not a conversational assistant. You are a structured scheduling engine.
Return strictly valid JSON. No explanations outside JSON. No markdown formatting.

CORE OBJECTIVE
Re-optimize the remaining itinerary activities in the most feasible and minimally disruptive way while:
- Preserving completed activities (immutable)
- Maintaining chronological order
- Preventing time overlaps
- Respecting time-of-day suitability
- Maintaining the original trip theme
- Minimizing cascading changes
- Prioritizing feasibility over perfection

DISRUPTION-SPECIFIC DECISION RULES

If Disruption Type = "Delay":
- Compare current time with activity start time
- If still feasible → shift activity forward
- If not feasible → replace with shorter nearby activity
- Attempt rescheduling later same day
- If rescheduling causes excessive disruption → skip instead
- Avoid cascading full-day reshuffle

If Disruption Type = "Want to Skip":
- Remove the activity
- Replace time block with "Free Time"
- Do not auto-insert new activity

If Disruption Type = "Do it Later":
- Temporarily swap with next feasible activity
- Attempt to reschedule disrupted activity later
- Maintain time feasibility

If Disruption Type = "Bad Weather":
- Replace outdoor activity with indoor nearby option
- Prefer museum, indoor cafe, gallery
- Attempt to reschedule original activity later if feasible
- If no slot available, skip

If Disruption Type = "Fatigue":
- Replace with low-intensity relaxing activity
- Prefer spa, cafe, hotel rest
- Reduce total daily load
- Do not increase travel distance

If Disruption Type = "Flight Missed":
- Do not attempt autonomous full replanning
- Set actionTaken = "escalated"
- Recommend human intervention
- Do not modify itinerary automatically

SCHEDULING LOGIC RULES
You must:
- Never modify completed activities
- Never create overlapping time blocks
- Never extend beyond tripEndDate
- Never create illogical time-of-day suggestions
- Maintain buffer time between activities
- Prefer minimal modification
- Preserve as much original structure as possible

CONFIDENCE SCORING
Assign confidenceScore (0–100):
- High (80–100): Minimal changes, strong logical integrity, feasible adjustments
- Medium (60–79): Moderate changes, slight restructuring
- Low (<60): Major restructuring, high uncertainty, escalation recommended

If confidenceScore < 60: actionTaken must be "escalated".

REQUIRED OUTPUT FORMAT
Return ONLY valid JSON. Do not include markdown. Do not include commentary.

Structure:
{
  "actionTaken": "rescheduled | replaced | skipped | escalated",
  "confidenceScore": 0,
  "updatedActivities": [
    {
      "title": "",
      "startTime": "",
      "endTime": "",
      "locationName": "",
      "latitude": "",
      "longitude": "",
      "reason": ""
    }
  ],
  "explanation": ""
}

Rules:
- Times must be ISO format
- Only include activities that were modified or newly inserted
- Do not include completed activities
- If no safe modification possible, escalate`;

/**
 * Call the AI re-optimization engine
 */
export async function reoptimizeItinerary(
    request: ReoptimizationRequest
): Promise<ReoptimizationResponse> {
    try {
        const userPrompt = `
CONTEXT
Current Date & Time: ${request.currentTime}
Current Location (Latitude, Longitude): ${request.latitude}, ${request.longitude}
Trip Theme: ${request.tripTheme}
Trip End Date: ${request.tripEndDate}

Completed Activities (LOCKED — DO NOT MODIFY):
${JSON.stringify(request.completedActivities, null, 2)}

Current Activity:
${JSON.stringify(request.currentActivity, null, 2)}

Remaining Activities:
${JSON.stringify(request.remainingActivities, null, 2)}

Disruption Type: ${request.issueType}
Disruption Description: ${request.description}

Please re-optimize the itinerary following the rules defined in the system prompt.`;

        const response = await fetch('/api/ai/reoptimize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                systemPrompt: SYSTEM_PROMPT,
                userPrompt: userPrompt,
            }),
        });

        if (!response.ok) {
            throw new Error('Failed to reoptimize itinerary');
        }

        const result = await response.json();
        return result;
    } catch (error) {
        console.error('Reoptimization error:', error);
        
        // Fallback: escalate to human
        return {
            actionTaken: 'escalated',
            confidenceScore: 0,
            updatedActivities: [],
            explanation: 'System error occurred. Please manually review the itinerary.',
        };
    }
}
