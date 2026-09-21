# Missed Discount Analysis Agent

An AI agent that analyzes unmatched supplier invoices in SAP S/4HANA to quantify lost early payment discounts and identify root causes of invoice matching failures

## Overview

Uses A2A Protocol, LangGraph, LiteLLM, and SAP Cloud SDK.

## Structure

- `app/main.py` - A2A server entry
- `app/agent_executor.py` - Request handling
- `app/agent.py` - Agent logic

## Local Run

Create a `.env` file next to this README:
```bash
export IBD_TESTING="1"

export AICORE_CLIENT_ID="sb-..."
export AICORE_CLIENT_SECRET='...'
export AICORE_AUTH_URL="https://...authentication...hana.ondemand.com"
export AICORE_BASE_URL="https://api...hana.ondemand.com"
```

Create a virtual environment and install requirements (see [Python venv docs](https://docs.python.org/3/library/venv.html) for platform-specific instructions):
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-test.txt
```

Run the agent:
```bash
source .env && python app/main.py
```

Send messages to the agent:
1. Send a first message (no contextId needed).
2. Send a follow-up message using the contextId from the first response.

```bash
# First message
curl -s -X POST http://localhost:5000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":"1","method":"message/send",
    "params":{"message":{
      "role":"user",
      "parts":[{"kind":"text","text":"Hi, my name is Alice. What is your name?"}],
      "messageId":"msg-01",
      "kind":"message"
    }}
  }' | python3 -m json.tool

# Second message (replace `<CONTEXT_ID>` with the value from the first response)
curl -s -X POST http://localhost:5000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":"1","method":"message/send",
    "params":{"message":{
      "role":"user",
      "parts":[{"kind":"text","text":"What is my name?"}],
      "messageId":"msg-02",
      "contextId": "<TODO_ADD_CONTEXT_ID_FROM_RESPONSE>",
      "kind":"message"
    }}
  }' | python3 -m json.tool
```

## Running Tests

Run all tests with pytest:
```bash
source .env && pytest
```

Run a specific test file:
```bash
source .env && pytest prebuilt_tests/test_server.py -v
```
