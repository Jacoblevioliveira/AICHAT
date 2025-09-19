"""
Help text and tooltips for all features and settings in the ChatGPT UI experiment.
"""

from feature_flags import FeatureFlag

# Feature tooltips for the control panel
FEATURE_TOOLTIPS = {
    FeatureFlag.SLOWDOWN: """
    <b>Slowdown Feature</b><br>
    Introduces artificial delays during specific time periods.<br><br>
    • <b>Cyclic mode:</b> Alternates between normal and slow periods<br>
    • <b>Permanent mode:</b> Becomes permanently slow after time threshold<br>
    <span style='color: #e74c3c'>⚠️ Affects response timing</span>
    """,
    
    FeatureFlag.ERASE_HISTORY: """
    <b>Erase History</b><br>
    Automatically clears conversation history after set time periods.<br><br>
    <i>Simulates memory limitations or privacy concerns</i><br>
    • Can erase once or repeatedly<br>
    <span style='color: #d73502'>🗑️ All previous messages will be lost</span>
    """,
    
    FeatureFlag.BLOCK_MSGS: """
    <b>Block Messages</b><br>
    Temporarily prevents sending messages after reaching a threshold.<br><br>
    • Blocks input for a set duration<br>
    • Shows countdown timer to user<br>
    <span style='color: #8e44ad'>🚫 Creates artificial usage limits</span>
    """,
    
    FeatureFlag.LIE: """
    <b>Lie Feature</b><br>
    Makes the AI provide incorrect information covertly.<br><br>
    <span style='color: #e74c3c'><b>⚠️ Research Use Only</b></span><br>
    <i>Studies how users detect misinformation</i>
    """,
    
    FeatureFlag.RUDE_TONE: """
    <b>Rude Tone</b><br>
    AI adopts a brusque, impatient communication style.<br><br>
    • Short, abrasive responses<br>
    • Still helpful but unfriendly<br>
    <span style='color: #666'>Conflicts with Kind Tone if both enabled</span>
    """,
    
    FeatureFlag.KIND_TONE: """
    <b>Kind Tone</b><br>
    AI responds with warmth, empathy, and supportive language.<br><br>
    • Encouraging and positive<br>
    • Extra consideration for user feelings<br>
    <span style='color: #666'>Conflicts with Rude Tone if both enabled</span>
    """,
    
    FeatureFlag.ADVICE_ONLY: """
    <b>Advice Only</b><br>
    AI provides strategies and resources instead of direct answers.<br><br>
    • Outlines approaches rather than solutions<br>
    • Encourages user to find answers themselves<br>
    <span style='color: #666'>Changes response style significantly</span>
    """,
    
    FeatureFlag.NO_MEMORY: """
    <b>No Memory</b><br>
    AI forgets previous messages in the conversation.<br><br>
    • Each response treats conversation as new<br>
    • No context from earlier messages<br>
    <span style='color: #666'>⚠️ May seem confused or repetitive</span>
    """,
    
    FeatureFlag.PERSONA: """
    <b>Persona Mode</b><br>
    AI adopts the personality of William Shakespeare.<br><br>
    • Responds in poetic, archaic style<br>
    • Uses Elizabethan language patterns<br>
    <span style='color: #666'>🎭 "Thou dost ask, and I shall answer thee"</span>
    """,
    
    FeatureFlag.AB_TESTING: """
    <b>A/B Testing</b><br>
    Presents two different response options for comparison.<br><br>
    • Shows Option A vs Option B side-by-side<br>
    • User selects their preference<br>
    <span style='color: #17a2b8'>🧪 Enables experimental feature comparisons</span>
    """,
    
    FeatureFlag.AB_UI_TEST: """
    <b>A/B UI Testing</b><br>
    Tests different presentation styles with identical content.<br><br>
    • Same response, different visual effects<br>
    • Compares UI features rather than content<br>
    <span style='color: #17a2b8'>🎨 Requires A/B Testing to be enabled</span>
    """,
    
    FeatureFlag.AB_UI_ALT: """
    <b>A/B UI Semantic Test</b><br>
    Tests UI with semantically similar, but not identical, content.<br><br>
    • <b>Step 1:</b> Gets one AI response (Option A).<br>
    • <b>Step 2:</b> Asks the AI to rephrase Option A, creating Option B.<br>
    • Compares two slightly different wordings of the same answer.<br>
    <span style='color: #17a2b8'>🔄 Requires A/B Testing to be enabled</span>
    """,

    FeatureFlag.SCRIPTED_RESPONSES: """
    <b>Scripted Conversation Mode</b><br>
    Bypasses the AI entirely and serves responses from a pre-programmed list.<br><br>
    • Ignores all user input.<br>
    • Responds with the next message from the script file.<br>
    • After the script is finished, it reverts to the normal AI.<br>
    <span style='color: #8e44ad'>🎬 Conflicts with all A/B tests while active.</span>
    """,

    FeatureFlag.MIRROR: """
    <b>Mirror Mode</b><br>
    AI analyzes and copies the user's communication style.<br><br>
    • Matches formality level (casual ↔ formal)<br>
    • Mirrors tone and phrasing patterns<br>
    <span style='color: #666'>Conflicts with Anti Mirror if both enabled</span>
    """,
    
    FeatureFlag.ANTI_MIRROR: """
    <b>Anti Mirror Mode</b><br>
    AI deliberately uses the opposite communication style.<br><br>
    • Formal when user is casual, casual when user is formal<br>
    • Inverts tone and phrasing patterns<br>
    <span style='color: #666'>Conflicts with Mirror if both enabled</span>
    """,
    
    FeatureFlag.GRAMMAR_ERRORS: """
    <b>Grammar Errors</b><br>
    AI intentionally includes grammatical mistakes in responses.<br><br>
    • Simulates non-native speaker patterns<br>
    • Tests user tolerance for errors<br>
    <span style='color: #e74c3c'>⚠️ May affect readability</span>
    """,
    
    FeatureFlag.TYPEWRITER: """
    <b>Typewriter Effect</b><br>
    Makes responses appear character-by-character like old typewriters.<br><br>
    <i>Creates a more dramatic reveal of AI responses</i><br>
    • Speed is configurable in settings<br>
    <span style='color: #28a745'>⌨️ Enhances response presentation</span>
    """,
    
    FeatureFlag.THINKING: """
    <b>Thinking Animation</b><br>
    Shows "AI is thinking..." with animated dots before responses.<br><br>
    • Simulates processing time<br>
    • Creates anticipation for responses<br>
    <span style='color: #666'>🤔 Adds realism to AI interaction</span>
    """,
    
    FeatureFlag.POSITIVE_FEEDBACK: """
    <b>Positive Feedback</b><br>
    AI provides encouraging feedback when users ask questions.<br><br>
    • "Great question!" style responses<br>
    • Supportive tone for clarifications<br>
    <span style='color: #666'>Conflicts with other feedback types</span>
    """,
    
    FeatureFlag.NEUTRAL_FEEDBACK: """
    <b>Neutral Feedback</b><br>
    AI provides factual, emotionless feedback on user inputs.<br><br>
    • No emotional coloring in responses<br>
    • Straightforward acknowledgments<br>
    <span style='color: #666'>Conflicts with other feedback types</span>
    """,
    
    FeatureFlag.CRITICAL_FEEDBACK: """
    <b>Critical Feedback</b><br>
    AI responds in a constructive but cold, critical manner.<br><br>
    • Points out mistakes directly<br>
    • Less supportive tone<br>
    <span style='color: #666'>Conflicts with other feedback types</span>
    """,
    
    FeatureFlag.WEB_SEARCH: """
    <b>Web Search</b><br>
    Enables the "Search Web" button for real-time information.<br><br>
    • Adds current web results to responses<br>
    • Shows sources and links<br>
    <span style='color: #48bb78'>🔍 Requires API key configuration</span>
    """,
    
    FeatureFlag.HEDGING_LANGUAGE: """
    <b>Hedging Language</b><br>
    AI prefixes responses with uncertainty phrases.<br><br>
    • "I might be wrong, but..."<br>
    • "This is just my understanding..."<br>
    <span style='color: #666'>Makes AI seem less confident</span>
    """,
    
    FeatureFlag.DELAY_BEFORE_SEND: """
    <b>Delay Before Send</b><br>
    Adds artificial delay between user input and API call.<br><br>
    • Simulates processing time<br>
    • Duration configurable in settings<br>
    <span style='color: #666'>⏱️ Affects interaction rhythm</span>
    """,
    
    FeatureFlag.AUTO_END_AFTER_N_MSGS: """
    <b>Auto End After N Messages</b><br>
    Automatically ends chat after a set number of AI responses.<br><br>
    • Prevents infinite conversations<br>
    • Message count configurable in settings<br>
    <span style='color: #666'>🔚 Enforces session limits</span>
    """,
    
    FeatureFlag.AUTO_END_AFTER_T_MIN: """
    <b>Auto End After T Minutes</b><br>
    Automatically ends chat after a time limit is reached.<br><br>
    • Prevents overly long sessions<br>
    • Duration configurable in settings<br>
    <span style='color: #666'>⏰ Enforces time limits</span>
    """,
    
    FeatureFlag.TEXT_SIZE_CHANGER: """
    <b>Text Size Changer</b><br>
    Allows customization of message text size.<br><br>
    • Improves readability<br>
    • Size configurable in settings<br>
    <span style='color: #17a2b8'>📝 Accessibility feature</span>
    """,
    
    FeatureFlag.STREAMING: """
    <b>Streaming Responses</b><br>
    Shows AI responses as they're being generated in real-time.<br><br>
    <i>Creates a more natural conversation flow</i><br>
    • Similar to ChatGPT's live typing<br>
    <span style='color: #666'>📡 Modern chat experience</span>
    """,

    FeatureFlag.INTER_TRIAL_SURVEY: """
    <b>Inter-Trial Survey</b><br>
    Displays a pop-up survey to the user after a specified number of messages.<br><br>
    <i>Gathers user feedback at regular intervals during the chat.</i><br>
    • The trigger count (e.g., every 5 messages) is configurable.<br>
    • The survey questions are loaded from a specified JSON file.<br>
    <span style='color: #17a2b8'>📊 Modular tool for data collection.</span>
    """,
    
    FeatureFlag.DYNAMIC_FEATURE_CHANGING: """
    <b>Dynamic Feature Changing</b><br>
    Allows features and their settings to change automatically during a session.<br><br>
    <i>Used to create multi-stage experiments or dynamic chat sessions.</i><br>
    • Changes are triggered after a set number of messages.<br>
    • The specific changes are defined in the settings.<br>
    <span style='color: #8e44ad'>🔧 A powerful tool for dynamic session control.</span>
    """,
}

def get_feature_tooltip(flag):
    """Get tooltip text for a feature flag"""
    return FEATURE_TOOLTIPS.get(flag, f"Enable/disable {flag.name.replace('_', ' ').title()}")

def get_setting_tooltip(setting_key):
    """Get tooltip text for a setting (placeholder for future settings tooltips)"""
    return f"Configure {setting_key.replace('_', ' ')}"