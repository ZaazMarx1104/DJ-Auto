#!/usr/bin/env python3
"""Test script to debug LLM responses"""

import asyncio
import json
import logging
from backend.app.config import get_settings
from backend.app import llm_client
from backend.app.prompts import SYSTEM_PROMPT

# Set up logging
logging.basicConfig(level=logging.INFO)

async def test_llm_response():
    """Test the LLM with a simple prompt"""
    
    # Simple test prompt
    test_prompt = """
User request: Simple 4/4 kick drum pattern for 2 bars

Context:
- Tempo: 120 BPM
- Time signature: 4/4
- Bars: 2 (total beats: 8)
- Role: drums
- Density: medium
- Register: low
- Pitch range: 35 to 45
- Max notes per bar: 4
- Quantize: 1/4

Task:
Design a musically coherent pattern that fits this role and context.
Return a single JSON object with a "notes" array only.
Every note must obey the pitch range and clip bounds.
"""
    
    print(f"Testing with Qwen 3 32B model: {get_settings().llm_model}")
    print(f"System prompt length: {len(SYSTEM_PROMPT)} characters")
    print(f"User prompt length: {len(test_prompt)} characters")
    print("\n" + "="*50)
    print("Calling LLM...")
    
    try:
        response = await llm_client._call_llm(SYSTEM_PROMPT, test_prompt)
        print("SUCCESS!")
        print(f"Response keys: {list(response.keys())}")
        print(f"Number of notes: {len(response.get('notes', []))}")
        if response.get('notes'):
            print("First note:", response['notes'][0])
        print("\nFull response:")
        print(json.dumps(response, indent=2))
        
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"Error type: {type(e)}")
        
if __name__ == "__main__":
    asyncio.run(test_llm_response())
