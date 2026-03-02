/**
 * Simple Gemini-based Reoptimizer
 * Directly reoptimizes itineraries and applies changes
 */

import { GoogleGenerativeAI } from '@google/generative-ai';

interface Activity {
    id?: number;
    time: string;
    title: string;
    location: string;
    notes?: string;
    status?: string;
    lat?: number;
    lng?: number;
    duration?: number;
}

interface ReoptimizationResult {
    success: boolean;
    message: string;
    updatedActivities?: Activity[];
}

export async function reoptimizeWithGemini(
    issueType: string,
    description: string,
    currentActivity: Activity,
    remainingActivities: Activity[],
    tripDestination: string
): Promise<ReoptimizationResult> {
    try {
        // Check if API key exists
        const apiKey = process.env.NEXT_PUBLIC_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
        if (!apiKey) {
            return {
                success: false,
                message: 'Gemini API key not configured. Please add GEMINI_API_KEY to .env.local'
            };
        }

        const genAI = new GoogleGenerativeAI(apiKey);
        const model = genAI.getGenerativeModel({ model: 'gemini-pro' });

        const prompt = `You are a travel itinerary optimizer. A disruption has occurred during a trip to ${tripDestination}.

DISRUPTION DETAILS:
- Type: ${issueType}
- Description: ${description}
- Current Activity: ${currentActivity.title} at ${currentActivity.time}
- Location: ${currentActivity.location}

REMAINING ACTIVITIES:
${remainingActivities.map((a, i) => `${i + 1}. ${a.title} at ${a.time} (${a.location})`).join('\n')}

TASK: Based on the disruption type, suggest how to handle the remaining activities.

RULES:
- If "Delay": Shift activities forward by 1-2 hours
- If "Want to Skip": Remove current activity, keep rest as-is
- If "Do it Later": Swap current with next activity
- If "Bad Weather": Replace outdoor activities with indoor alternatives
- If "Fatigue": Add rest time, reduce intensity

Respond with ONLY a JSON array of updated activities in this format:
[
  {
    "time": "HH:MM",
    "title": "Activity Name",
    "location": "Location Name",
    "notes": "Any changes made",
    "duration": 2
  }
]

Keep it simple and practical. Only modify what's necessary.`;

        const result = await model.generateContent(prompt);
        const response = result.response;
        const text = response.text();

        // Parse JSON from response
        let activities: Activity[] = [];
        try {
            // Extract JSON from markdown if present
            let jsonText = text.trim();
            if (jsonText.includes('```json')) {
                jsonText = jsonText.split('```json')[1].split('```')[0].trim();
            } else if (jsonText.includes('```')) {
                jsonText = jsonText.split('```')[1].split('```')[0].trim();
            }
            
            // Remove any text before [ and after ]
            const startIndex = jsonText.indexOf('[');
            const endIndex = jsonText.lastIndexOf(']');
            if (startIndex !== -1 && endIndex !== -1) {
                jsonText = jsonText.substring(startIndex, endIndex + 1);
            }
            
            activities = JSON.parse(jsonText);
        } catch (parseError) {
            console.error('Failed to parse Gemini response:', text);
            return {
                success: false,
                message: 'AI returned invalid format. Manual review needed.'
            };
        }

        return {
            success: true,
            message: `Itinerary reoptimized based on ${issueType}. ${activities.length} activities updated.`,
            updatedActivities: activities
        };

    } catch (error: any) {
        console.error('Gemini reoptimization error:', error);
        return {
            success: false,
            message: `Error: ${error.message || 'Unknown error occurred'}`
        };
    }
}
