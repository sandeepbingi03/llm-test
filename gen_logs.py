import json
import random
from datetime import datetime, timedelta
from faker import Faker
import spacy
from collections import defaultdict

# Initialize components
fake = Faker()
nlp = spacy.load("en_core_web_sm")
alert_distribution = defaultdict(int)
error_keywords = ["fail", "error", "timeout", "exception", "crash", "null", "undefined"]

def generate_dataset(input_logs_path, output_path, num_examples=1000):
    # Load existing logs
    with open(input_logs_path) as f:
        logs = [json.loads(line) for line in f]
    
    # Sort logs chronologically
    logs.sort(key=lambda x: datetime.fromisoformat(x["event_time"]))
    
    # Generate training examples
    examples = []
    
    # 1. Create real examples from log sequences
    examples += create_temporal_windows(logs)
    
    # 2. Create cross-service correlation examples
    examples += create_correlation_examples(logs)
    
    # 3. Generate synthetic examples
    examples += generate_synthetic_examples(num_examples=num_examples//3)
    
    # 4. Add negative examples
    examples += create_negative_examples(logs)
    
    # Save dataset
    with open(output_path, 'w') as f:
        for ex in examples:
            f.write(json.dumps(ex) + '\n')
    
    print(f"Generated {len(examples)} examples")
    print("Alert distribution:", dict(alert_distribution))

def create_temporal_windows(logs, window_size=5):
    windows = []
    current_window = []
    window_end = None
    
    for log in logs:
        log_time = datetime.fromisoformat(log["event_time"])
        
        if not current_window:
            current_window.append(log)
            window_end = log_time + timedelta(minutes=window_size)
        else:
            if log_time <= window_end:
                current_window.append(log)
            else:
                if len(current_window) >= 2:
                    windows.append(process_window(current_window))
                current_window = [log]
                window_end = log_time + timedelta(minutes=window_size)
    
    return windows

def process_window(window):
    # Analyze window content
    analysis = analyze_log_group(window)
    
    # Build example
    example = {
        "instruction": "Analyze these application logs. Consider message content, exceptions, and patterns across fields. Determine system health status and explain your reasoning.",
        "input": window,
        "output": format_output(analysis)
    }
    
    alert_distribution[analysis["level"]] += 1
    return example

def analyze_log_group(logs):
    # Calculate metrics
    metrics = {
        "error_count": 0,
        "hidden_errors": 0,
        "exceptions": set(),
        "services": set(),
        "correlation_ids": set(),
        "messages": []
    }
    
    for log in logs:
        # Count explicit errors
        if log["log_level"] in ["ERROR", "CRITICAL"]:
            metrics["error_count"] += 1
        
        # Detect hidden errors
        message = log["message"].lower()
        if any(kw in message for kw in error_keywords):
            metrics["hidden_errors"] += 1
        
        # Track exceptions
        if log["exception"]:
            metrics["exceptions"].add(log["exception"])
        
        # Track context
        metrics["services"].add(log["app_name"])
        if log["correlation_id"]:
            metrics["correlation_ids"].add(log["correlation_id"])
        metrics["messages"].append(log["message"])
    
    # Determine alert level
    return calculate_alert_level(metrics, len(logs))

def calculate_alert_level(metrics, total_logs):
    score = 0
    reasons = []
    
    # Scoring
    score += metrics["error_count"] * 2
    score += metrics["hidden_errors"] * 1.5
    score += len(metrics["exceptions"]) * 3
    if len(metrics["services"]) > 1:
        score += 4
    if len(metrics["correlation_ids"]) > 0:
        score += 2
    
    # Determine level
    if score >= 10:
        level = "CRITICAL"
    elif score >= 6:
        level = "HIGH"
    elif score >= 3:
        level = "LOW"
    else:
        level = "NORMAL"
    
    # Build reasons
    if metrics["error_count"]:
        reasons.append(f"{metrics['error_count']} explicit errors")
    if metrics["hidden_errors"]:
        reasons.append(f"{metrics['hidden_errors']} hidden errors in messages")
    if metrics["exceptions"]:
        reasons.append(f"{len(metrics['exceptions']} unique exceptions")
    if len(metrics["services"]) > 1:
        reasons.append(f"multiple services affected ({', '.join(metrics['services'])})")
    
    return {
        "level": level,
        "reasons": reasons,
        "sample_messages": random.sample(metrics["messages"], min(3, len(metrics["messages"])))
    }

def format_output(analysis):
    if analysis["level"] == "NORMAL":
        return f"Alert Level: NORMAL\nObservation: System operating within expected parameters"
    
    reasons = "\n- ".join(analysis["reasons"])
    samples = "\n- ".join(analysis["sample_messages"])
    return f"""Alert Level: {analysis['level']}
Observation:
- {reasons}

Relevant Messages:
- {samples}"""

def create_correlation_examples(logs):
    # Group logs by correlation_id
    correlation_groups = defaultdict(list)
    for log in logs:
        if log["correlation_id"]:
            correlation_groups[log["correlation_id"]].append(log)
    
    # Create examples for groups with >1 log
    examples = []
    for cid, group in correlation_groups.items():
        if len(group) > 1:
            examples.append(process_window(group))
    return examples

def generate_synthetic_examples(num_examples):
    synthetic = []
    for _ in range(num_examples):
        logs = []
        num_logs = random.randint(2, 5)
        correlation_id = fake.uuid4() if random.random() > 0.7 else None
        
        for _ in range(num_logs):
            log = {
                "event_time": fake.iso8601(),
                "log_level": random.choice(["INFO", "WARN", "ERROR"]),
                "app_name": random.choice(["payments", "inventory", "auth", "shipping"]),
                "message": generate_synthetic_message(),
                "exception": random.choice(["", "NullPointerException", "DatabaseTimeout", "SecurityException"]),
                "correlation_id": correlation_id,
                "transaction_id": fake.uuid4() if random.random() > 0.5 else None
            }
            logs.append(log)
        
        synthetic.append(process_window(logs))
    return synthetic

def generate_synthetic_message():
    template = random.choice([
        "{} processing {} request",
        "{} occurred during {} operation",
        "{} while handling {}",
        "Completed {} with status: {}"
    ])
    
    parts = [
        random.choice(["Successfully", "Failed to", "Attempting", "Aborted"]),
        random.choice(["payment", "database", "authentication", "inventory"])
    ]
    
    message = template.format(*parts)
    
    # Add error indicators 30% of time
    if random.random() < 0.3:
        message += " - " + random.choice([
            f"{random.randint(2,5)} retry attempts",
            "timeout after 5000ms",
            "invalid credentials",
            "connection refused"
        ])
    
    return message

def create_negative_examples(logs):
    negatives = []
    for log in logs:
        # Create misleading but normal scenarios
        if log["log_level"] == "ERROR" and "maintenance" in log["message"].lower():
            new_log = log.copy()
            new_log["message"] += " - scheduled downtime"
            negatives.append(process_window([new_log]))
        
        # Create false error patterns
        if log["log_level"] == "INFO" and "error" in log["message"].lower():
            new_log = log.copy()
            new_log["message"] = log["message"].replace("error", "status")
            negatives.append(process_window([new_log]))
    
    return negatives

if __name__ == "__main__":
    generate_dataset(
        input_logs_path="preprocessed_logs.jsonl",
        output_path="fine_tuning_dataset.jsonl",
        num_examples=1500
    )
