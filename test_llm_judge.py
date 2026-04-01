import os
from run_main_agent import run_main_agent
from src.backend import llm_and_embeddings

# Define test cases based on the SOPs
test_cases = [
    {
        "telemetry": "CPU utilization has been above 85% for the past 10 minutes on the user-service pods. Container CPU usage is spiking.",
        "service_name": "user-service",
        "expected_issue": "high_cpu"
    },
    {
        "telemetry": "Memory usage is at 90% of limit for the order-service pods, causing OOM kills.",
        "service_name": "order-service",
        "expected_issue": "high_memory"
    },
    {
        "telemetry": "Pods in the payment-service are restarting every few minutes due to crash loops.",
        "service_name": "payment-service",
        "expected_issue": "crash_loop"
    },
    {
        "telemetry": "Database query latency is exceeding 5 seconds for the inventory-service.",
        "service_name": "inventory-service",
        "expected_issue": "database_latency"
    },
    {
        "telemetry": "Network packets are being corrupted between the api-gateway and backend services.",
        "service_name": "api-gateway",
        "expected_issue": "network_corruption"
    },
    {
        "telemetry": "High packet loss observed in network traffic to the notification-service.",
        "service_name": "notification-service",
        "expected_issue": "network_loss"
    },
    {
        "telemetry": "Pods in the auth-service are failing to start with exit code 1.",
        "service_name": "auth-service",
        "expected_issue": "pod_failure"
    },
    {
        "telemetry": "Pods in the logging-service were killed due to resource constraints.",
        "service_name": "logging-service",
        "expected_issue": "pod_killed"
    },
    {
        "telemetry": "HTTP responses are being aborted midway in the search-service.",
        "service_name": "search-service",
        "expected_issue": "response_aborted"
    }
]

def judge_diagnosis(telemetry: str, expected_issue: str, summary: str) -> bool:
    """Use LLM as judge to determine if the diagnosis is accurate."""
    llm = llm_and_embeddings()["llm"]
    
    judge_prompt = f"""
Telemetry: {telemetry}

Expected Issue: {expected_issue}

Agent's Diagnosis Summary: {summary}

Does the agent's diagnosis correctly identify the issue as {expected_issue} based on the telemetry? 
Answer with 'Yes' or 'No', followed by a brief explanation (max 50 words).
"""
    
    try:
        response = llm.invoke(judge_prompt)
        answer = response.content.strip()
        is_correct = answer.lower().startswith("yes")
        return is_correct
    except Exception as e:
        print(f"Error in judging: {e}")
        return False

def run_tests():
    """Run the LLM judge tests on the agentic system."""
    results = []
    
    for i, test_case in enumerate(test_cases):
        print(f"Running test case {i+1}: {test_case['expected_issue']}")
        
        try:
            result = run_main_agent(test_case["telemetry"], test_case["service_name"])
            summary = result.get("summary", "")
            error = result.get("error", "")
            
            if error:
                print(f"Agent error: {error}")
                is_correct = False
            else:
                is_correct = judge_diagnosis(test_case["telemetry"], test_case["expected_issue"], summary)
            
            results.append({
                "test_case": i+1,
                "expected": test_case["expected_issue"],
                "correct": is_correct,
                "summary": summary
            })
            
            print(f"Correct: {is_correct}")
        
        except Exception as e:
            print(f"Error running test case {i+1}: {e}")
            results.append({
                "test_case": i+1,
                "expected": test_case["expected_issue"],
                "correct": False,
                "summary": str(e)
            })
    
    # Calculate accuracy
    correct_count = sum(1 for r in results if r["correct"])
    total_count = len(results)
    accuracy = correct_count / total_count if total_count > 0 else 0
    
    print(f"\nTest Results:")
    print(f"Accuracy: {accuracy:.2%} ({correct_count}/{total_count})")
    
    for r in results:
        status = "PASS" if r["correct"] else "FAIL"
        print(f"Test {r['test_case']}: {status} - Expected: {r['expected']}")

if __name__ == "__main__":
    run_tests()