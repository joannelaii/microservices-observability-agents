import run_main_agent
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage
from src.graph import build_graph
import os


class ObservabilityBotManager:
    """Manages the observability graph for Telegram."""

    def __init__(self):
        self.graph = build_graph()

    def process_input(self, text: str, service_name: str = "opentelemetry-collector") -> str:
        """
        Process user input and return diagnosis.
        Automatically detects trace ID vs alarm text.
        """
        trace_id = self._detect_trace_id(text)
        telemetry = text if not trace_id else f"Trace ID: {trace_id}"

        try:
            result = self.graph.invoke({
                "messages": [HumanMessage(content=text)],
                "telemetry": telemetry,
                "service_name": service_name,
                "trace_id": trace_id,
                "diagnostic_plan": None,
                "sop_guidance": None,
                "code_analysis": None,
                "reasoning_output": None,
                "root_cause_found": False,
                "next_action": "",
                "summary": None,
                "error": None,
            })

            summary = result.get("summary") or result.get("diagnostic_plan") or "No diagnosis available."
            return self._format_response(summary)

        except Exception as e:
            return f" Error: {type(e).__name__}: {str(e)}"

    @staticmethod
    def _detect_trace_id(text: str) -> str | None:
        """Detect if text is a trace ID (hex string or UUID format)."""
        text = text.strip()
        
        # UUID format: 8-4-4-4-12 hex digits
        if len(text) == 36 and text.count("-") == 4:
            try:
                int(text.replace("-", ""), 16)
                return text
            except ValueError:
                pass
        
        # Hex string without dashes, 16-32 chars
        if 16 <= len(text) <= 64 and " " not in text and "-" not in text:
            try:
                int(text, 16)
                return text
            except ValueError:
                pass

        # Generic segmented trace token (e.g., abc-123-def-456)
        if re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}", text):
            return text
        
        return None

    @staticmethod
    def _format_response(summary: str) -> str:
        """Format diagnosis into readable Telegram message."""
        lines = summary.split("\n")[:10]  # Limit to 10 lines for readability
        return "\n".join(lines) or "No diagnosis available."


# Global bot instance
bot_manager = ObservabilityBotManager()


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Telegram messages."""
    user_text = update.message.text
    chat_id = update.effective_chat.id

    response = bot_manager.process_input(user_text)
    await context.bot.send_message(chat_id=chat_id, text=response)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome = (
        "Welcome to Microservices Observability Bot!\n\n"
        "Send me:\n"
        "• An alarm/alert description (e.g., 'high CPU, pod restarting')\n"
        "• A trace ID (e.g., 'abc123def456')\n\n"
        "I'll diagnose the issue and suggest fixes."
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome)


def main():
    """Start the Telegram bot."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_TOKEN environment variable not set")
        return

    app = ApplicationBuilder().token(token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    
    print("Bot started (polling)")
    app.run_polling()


if __name__ == "__main__":
    main()