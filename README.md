# Microservices Observability Agents

## Overview
This project provides observability agents for microservices architecture.

## Project Structure
```
src/
├── main.py          # Main entry point
└── tests/           # Test suite
```

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd microservices-observability-agents
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Project

### Start the Application
```bash
python src/main.py
```

### Run Tests
Run the test scripts directly:

```bash
python src/tests/test_main.py
python src/tests/test_reasoning.py
python src/tests/test_llm_judge.py
```

## Configuration
Update configuration files as needed before running the application.

## Documentation
For detailed documentation, refer to relevant docstrings in the source code.