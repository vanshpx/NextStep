/**
 * Simple NLP-simulating utility to summarize long issue descriptions into concise snippets.
 * In a production app, this would call an LLM API (like Gemini).
 */
export async function summarizeIssue(type: string, description: string): Promise<string> {
    if (!description || description.trim().length === 0) return type;

    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 600));

    const text = description.toLowerCase();

    // Simple rule-based extraction for "NLP" feel
    const timeMatch = description.match(/(\d+)\s*(hour|hr|min|minute|day)/i);
    const reasonMatch = text.match(/(weather|traffic|storm|snow|rain|medical|sick|lost|broke|technical|strike|closed|hungry|tired|exhausted|busy|no power|internet)/);

    let summary = type;

    if (reasonMatch) {
        summary += ` - due to ${reasonMatch[0]}`;
        if (timeMatch) {
            summary += ` (${timeMatch[0]})`;
        }
    } else if (timeMatch) {
        summary += ` - ${timeMatch[0]} delay`;
    }

    // Fallback: If no specific keywords found, return the description "as it is"
    if (summary === type) {
        summary = description;
    }

    return summary;
}
