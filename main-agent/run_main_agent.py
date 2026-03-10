import os
from src.graph import build_graph

if __name__ == "__main__":
    alert = os.getenv("ALERT_PAYLOAD")
    service = os.getenv("SERVICE_NAME")

    app = build_graph()
    result = app.invoke({
        "alert": alert,
        "service_name": service,
        "sop_guidance": None,
        "code_analysis": None,
        "reasoning_output": None,
        "summary": None,
        "error": None,
    })
    
    print(result)