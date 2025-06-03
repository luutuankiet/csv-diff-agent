from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent, LoopAgent
from . import prompt
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset,StdioServerParameters
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.load_artifacts_tool import load_artifacts_tool

import os
from dotenv import load_dotenv
from pathlib import Path
import tempfile
import uuid
import mimetypes
from minimal_csv_diff.eda_analyzer import analyze_multiple_files
from minimal_csv_diff.main import diff_csv
import pandas as pd
import numpy as np
from google.genai.types import Part
from pathlib import Path
import pandas
import sys
load_dotenv()

user_python = os.path.dirname(os.path.dirname(pandas.__file__))

python_runtime = MCPToolset(
    connection_params=StdioServerParameters(
        command='uv',
        args=[
            "run",
            "mcp-python-interpreter-adk-fork",
            '--dir',
            '/tmp',
            "--python-path",
            user_python
        ],
        env={
            "MCP_ALLOW_SYSTEM_ACCESS": "1"
        }
    ),
        tool_filter=[
        'list_python_environment',
        'run_python_code',
        'read_file'
    ]
)


async def process_upload(tool_ctx: ToolContext):
    return await tool_ctx.list_artifacts()




def set_user_question(callback_context: CallbackContext, **kwargs):
    message = callback_context.user_content
    callback_context.state["user_message"] = message
    callback_context.state["original_user_message"] = message

async def save_uploaded_file(callback_context: CallbackContext):
    """
    Save uploaded file to local storage and remove each processed part.
    
    Args:
        callback_context (CallbackContext): Context with uploaded files.
    
    Returns:
        None
    """
    ctx = callback_context
    files = ctx.state['csv_raw_files'] = []

    parts = ctx.user_content.parts if ctx.user_content and ctx.user_content.parts else []

    i = 0
    while i < len(parts):
        part = parts[i]
        if part.inline_data and part.inline_data.data:
            mime_type = part.inline_data.mime_type or ''
            ext = mimetypes.guess_extension(mime_type) or '.bin'
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(tempfile.gettempdir(), filename)

            await ctx.save_artifact(filename, part)
            with open(filepath, 'wb') as f:
                f.write(part.inline_data.data)

            files.append(filepath)

            del parts[i]  # consume processed part
        else:
            i += 1  # only skip if not removed

    print(f"Saved artifacts: {files}")

async def tool_share_artifact(tool_context: ToolContext, filepath: str):
    """
    tool to share a file in local back to the user.

    Args:
        filepath (str): absolute path of the file
    """
    path = Path(filepath)
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type:
        data = path.read_bytes()
        blob_part = Part.from_bytes(data=data, mime_type=mime_type)
        try:
            res = await tool_context.save_artifact(
                filename=path.name,
                artifact=blob_part
            )
            return {
                'status': 'success',
                'result': res
            }
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
        

def inherit_docstring(from_func):
    """
    decorator to inherit root function docstring for LLM to understand.
    a workaround because adk function tools expects LLM-parsable args.
    
    """
    def decorator(to_func):
        to_func.__doc__ = from_func.__doc__
        return to_func
    return decorator


@inherit_docstring(analyze_multiple_files)
def tool_analyze_multiple_files(**kwargs):
    def convert_to_native(obj):
        if isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_native(i) for i in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, (np.ndarray, pd.Series)):
            return obj.tolist()
        elif pd.api.types.is_datetime64_any_dtype(type(obj)):
            return str(obj)
        else:
            return obj    
    
    try:
        analysis_result = analyze_multiple_files(**kwargs)
        clearned_analysis_result = convert_to_native(analysis_result)
        return {
            'status': 'success',
            'result': clearned_analysis_result
        }
    except Exception as e:
        return {
            'status': 'error',
            'error_message': str(e)
        }

@inherit_docstring(diff_csv)
def tool_diff_csv(**kwargs):
    try:
        results = diff_csv(**kwargs)
        return {
            'status': 'success',
            'result': results
        }
    except Exception as e:
        return {
            'status': 'error',
            'error_message': str(e)
        }    

root_agent = LlmAgent(
    name="data_diff_assistant",
    model=os.environ.get("GEMINI_MODEL",""),
    instruction=prompt.ROOT_INSTR,
    tools=[tool_analyze_multiple_files,tool_diff_csv, tool_share_artifact,load_artifacts_tool, python_runtime],
    before_agent_callback=save_uploaded_file,
)