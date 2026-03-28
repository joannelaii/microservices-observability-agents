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

    def process_input(self, text: str, service_name: str = "opentelemetry-collector", time_window: str = "1h") -> str:
        """
        Process user input and return diagnosis.
        Automatically detects trace ID vs alarm text.
        """
        trace_id, parsed_window = self._extract_trace_and_window(text)
        telemetry = text if not trace_id else f"Trace ID: {trace_id}"
        effective_window = parsed_window or time_window

        try:
            result = self.graph.invoke({
                "messages": [HumanMessage(content=text)],
                "telemetry": telemetry,
                "service_name": service_name,
                "trace_id": trace_id,
                "time_window": effective_window if trace_id else None,
                "triage_metadata": None,
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
        """Detect if a token is a trace ID (hex string, UUID, or segmented format)."""
        text = text.strip().strip("'\"")
        if not text:
            return None
        
        # UUID format: 8-4-4-4-12 hex digits
        if len(text) == 36 and text.count("-") == 4:
            try:
                int(text.replace("-", ""), 16)
                return text
            except ValueError:
                pass
        
        # Hex string without dashes, 8-64 chars (must include at least one digit)
        if re.fullmatch(r"[A-Fa-f0-9]{8,64}", text) and re.search(r"\d", text):
            return text

        # Generic segmented trace token (e.g., abc-123-def-456)
        if re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}", text) and re.search(r"\d", text):
            return text
        
        return None

    @classmethod
    def _extract_trace_and_window(cls, text: str) -> tuple[str | None, str | None]:
        """
        Parse input like:
        - "abc123def456, 20 minutes"
        - "abc123def456 20m"
        - "abc123def456"
        Returns (trace_id, normalized_time_window).
        """
        raw = (text or "").strip()
        if not raw:
            return None, None

        # Preferred explicit split: trace_id, time window
        if "," in raw:
            first, rest = raw.split(",", 1)
            trace_id = cls._detect_trace_id(first.strip())
            if trace_id:
                return trace_id, cls._parse_time_window(rest.strip())

        # Fallback: whole text is just trace_id
        whole = cls._detect_trace_id(raw)
        if whole:
            return whole, None

        # Fallback: first token is trace_id, remainder may be time window
        first_token, sep, remainder = raw.partition(" ")
        token_trace = cls._detect_trace_id(first_token)
        if token_trace and sep:
            return token_trace, cls._parse_time_window(remainder.strip())

        return None, None

    @staticmethod
    def _parse_time_window(text: str) -> str | None:
        """Normalize common human time windows to short form (e.g., 20m, 1h, 2d)."""
        if not text:
            return None

        cleaned = text.strip().lower()
        match = re.fullmatch(
            r"(?P<value>\d+)\s*(?P<unit>m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)",
            cleaned,
        )
        if not match:
            return None

        value = match.group("value")
        unit = match.group("unit")

        if unit.startswith("m"):
            suffix = "m"
        elif unit.startswith("h"):
            suffix = "h"
        else:
            suffix = "d"

        return f"{value}{suffix}"

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
        "• A trace ID (e.g., 'abc123def456')\n"
        "• A trace ID with window (e.g., 'abc123def456, 20 minutes')\n\n"
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