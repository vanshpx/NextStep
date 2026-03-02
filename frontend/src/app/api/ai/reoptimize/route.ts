import { NextResponse } from 'next/server';
import { GoogleGenerativeAI } from '@google/generative-ai';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
    try {
        const { issueType, description, currentActivity, remainingActivities, destination } = await request.json();

        if (!issueType || !currentActivity || !remainingActivities) {
            return NextResponse.json(
                { error: 'Missing required fields' },
                { status: 400 }
            );
        }

        // Check if API key is configured
        if (!process.env.GEMINI_API_KEY) {
            console.error('GEMINI_API_KEY is not configured');
            return NextResponse.json(
                { 
                    success: false,
                    message: 'AI service is not configured. Please add GEMINI_API_KEY to your environment variables.',
                    updatedActivities: []
                },
                { status: 200 }
            );
        }

        const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
        const model = genAI.getGenerativeModel({ 
            model: 'gemini-2.5-flash', // Using the latest fast model
            generationConfig: {
                temperature: 0.3,
                maxOutputTokens: 4096,
            }
        });

        // Build the prompt with strict JSON formatting instructions
        const prompt = `You are a travel itinerary optimizer. A disruption has occurred during a trip to ${destination || 'the destination'}.

DISRUPTION DETAILS:
- Type: ${issueType}
- Description: ${description || 'No additional details'}
- Current Activity: ${currentActivity.title} at ${currentActivity.time}
- Location: ${currentActivity.location}

REMAINING ACTIVITIES:
${remainingActivities.map((a: any, i: number) => `${i + 1}. ID:${a.id} - ${a.title} at ${a.time} (${a.location})`).join('\n')}

TASK: Based on the disruption type, reoptimize the remaining activities.

RULES:
- If "Delay": Shift all activities forward by 1-2 hours
- If "Want to Skip": Keep remaining activities as-is with same times
- If "Do it Later": Swap current with next activity, adjust times
- If "Bad Weather": Replace outdoor activities with indoor alternatives nearby
- If "Fatigue": Add 30-60 min rest, reduce intensity of next activities

CRITICAL: You MUST respond with ONLY valid JSON. No explanations, no markdown, no extra text.
Return a JSON array with this EXACT structure:

[
  {
    "id": 123,
    "time": "14:30",
    "title": "Activity Name",
    "location": "Location Name",
    "notes": "Brief change description"
  }
]

IMPORTANT:
- Include ALL remaining activities (${remainingActivities.length} activities)
- Use the exact ID numbers from the list above
- Time format must be "HH:MM" (24-hour format)
- Keep changes minimal and realistic
- No markdown code blocks, just pure JSON`;

        const result = await model.generateContent(prompt);
        const response = result.response;
        const text = response.text();

        console.log('Gemini raw response:', text);

        // Parse JSON from response with improved error handling
        let activities: any[] = [];
        try {
            let jsonText = text.trim();
            
            // Remove markdown code blocks if present
            if (jsonText.includes('```json')) {
                const match = jsonText.match(/```json\s*([\s\S]*?)\s*```/);
                if (match) jsonText = match[1].trim();
            } else if (jsonText.includes('```')) {
                const match = jsonText.match(/```\s*([\s\S]*?)\s*```/);
                if (match) jsonText = match[1].trim();
            }
            
            // Find JSON array boundaries
            const startIndex = jsonText.indexOf('[');
            const endIndex = jsonText.lastIndexOf(']');
            
            if (startIndex === -1 || endIndex === -1) {
                throw new Error('No JSON array found in response');
            }
            
            jsonText = jsonText.substring(startIndex, endIndex + 1);
            
            // Parse the JSON
            activities = JSON.parse(jsonText);
            
            // Validate the structure
            if (!Array.isArray(activities)) {
                throw new Error('Response is not an array');
            }
            
            if (activities.length === 0) {
                throw new Error('Empty activities array');
            }
            
            // Validate each activity has required fields
            for (const activity of activities) {
                if (!activity.id || !activity.time || !activity.title || !activity.location) {
                    throw new Error(`Invalid activity structure: ${JSON.stringify(activity)}`);
                }
            }
            
            console.log('Parsed activities:', activities);
            
        } catch (parseError: any) {
            console.error('Failed to parse Gemini response:', text);
            console.error('Parse error:', parseError.message);
            return NextResponse.json({
                success: false,
                message: `AI response parsing failed: ${parseError.message}. Please try again.`,
                updatedActivities: [],
                rawResponse: text.substring(0, 500) // Include first 500 chars for debugging
            });
        }

        return NextResponse.json({
            success: true,
            message: `Itinerary reoptimized based on ${issueType}. ${activities.length} activities updated.`,
            updatedActivities: activities
        });
    } catch (error: any) {
        console.error('AI reoptimization error:', error);
        return NextResponse.json(
            { 
                success: false,
                message: `Error: ${error.message || 'Unknown error occurred'}`,
                updatedActivities: []
            },
            { status: 200 }
        );
    }
}
