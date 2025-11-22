"""Utility for loading and processing custom rule documents"""

import logging
from pathlib import Path
from typing import List, Optional

from ..core.config import AgentConfig

logger = logging.getLogger(__name__)


async def load_and_summarize_rules(rule_paths: List[str], config: AgentConfig) -> Optional[str]:
    """
    Load custom rule files and summarize them using LLM.
    
    Args:
        rule_paths: List of paths to markdown rule files
        config: Agent configuration with LLM settings
        
    Returns:
        Summarized rules as a string, or None if no valid rules found
    """
    if not rule_paths:
        return None
    
    # Load all rule files
    rule_contents = []
    for rule_path in rule_paths:
        try:
            path = Path(rule_path)
            if not path.exists():
                logger.warning(f"Rule file not found: {rule_path}")
                continue
            
            if not path.is_file():
                logger.warning(f"Rule path is not a file: {rule_path}")
                continue
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    rule_contents.append({
                        'file': path.name,
                        'content': content
                    })
                    logger.info(f"Loaded rule file: {path.name}")
        except Exception as e:
            logger.error(f"Error loading rule file {rule_path}: {e}")
            continue
    
    if not rule_contents:
        logger.warning("No valid rule files loaded")
        return None
    
    # If only one rule file, return it directly
    if len(rule_contents) == 1:
        logger.info("Single rule file loaded, using content directly")
        return rule_contents[0]['content']
    
    # Multiple rule files - use LLM to summarize and consolidate
    logger.info(f"Summarizing {len(rule_contents)} rule files using LLM")
    
    try:
        # Build prompt for summarization
        combined_rules = "\n\n---\n\n".join([
            f"## Rule File: {rule['file']}\n\n{rule['content']}"
            for rule in rule_contents
        ])
        
        summarization_prompt = f"""You are a code analysis expert. The user has provided multiple custom rule documents for analyzing their codebase.

Your task is to consolidate these rules into a single, coherent set of analysis guidelines.

REQUIREMENTS:
1. Preserve all important rules and guidelines from each document
2. Remove redundancy - if multiple documents mention the same rule, consolidate it
3. Organize rules logically by category (security, performance, style, etc.)
4. Keep the language clear and actionable
5. Maintain the priority and emphasis indicated in the original rules
6. Output should be concise but comprehensive

CUSTOM RULE DOCUMENTS:

{combined_rules}

OUTPUT FORMAT:
Provide a consolidated set of rules in markdown format. Use clear headings and bullet points. Be direct and specific."""

        # Configure Gemini
        if not config.use_local:
            import google.generativeai as genai
            
            genai.configure(api_key=config.google_api_key)
            model = genai.GenerativeModel(config.gemini_model)
            
            response = model.generate_content(
                summarization_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,  # Lower temperature for more consistent summarization
                    max_output_tokens=4096,
                )
            )
            
            summarized_rules = response.text.strip()
            logger.info("Successfully summarized custom rules")
            return summarized_rules
        else:
            # For local LLM (Ollama), use a simpler approach
            import ollama
            
            response = ollama.generate(
                model=config.ollama_model,
                prompt=summarization_prompt,
                options={
                    'temperature': 0.3,
                    'num_predict': 4096,
                }
            )
            
            summarized_rules = response['response'].strip()
            logger.info("Successfully summarized custom rules using local LLM")
            return summarized_rules
            
    except Exception as e:
        logger.error(f"Error summarizing rules with LLM: {e}")
        logger.info("Falling back to concatenation of rule files")
        
        # Fallback: simple concatenation
        fallback_rules = "\n\n".join([
            f"# {rule['file']}\n\n{rule['content']}"
            for rule in rule_contents
        ])
        return fallback_rules


def load_and_summarize_rules_sync(rule_paths: List[str], config: AgentConfig) -> Optional[str]:
    """
    Synchronous wrapper for load_and_summarize_rules.
    
    Args:
        rule_paths: List of paths to markdown rule files
        config: Agent configuration with LLM settings
        
    Returns:
        Summarized rules as a string, or None if no valid rules found
    """
    import asyncio
    
    # Check if we're already in an event loop
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, can't use asyncio.run
        logger.warning("Already in event loop, using synchronous rule loading")
        return _load_and_summarize_rules_blocking(rule_paths, config)
    except RuntimeError:
        # No event loop running, safe to use asyncio.run
        return asyncio.run(load_and_summarize_rules(rule_paths, config))


def _load_and_summarize_rules_blocking(rule_paths: List[str], config: AgentConfig) -> Optional[str]:
    """
    Blocking version of rule loading and summarization.
    Used when already in an async context.
    """
    if not rule_paths:
        return None
    
    # Load all rule files
    rule_contents = []
    for rule_path in rule_paths:
        try:
            path = Path(rule_path)
            if not path.exists():
                logger.warning(f"Rule file not found: {rule_path}")
                continue
            
            if not path.is_file():
                logger.warning(f"Rule path is not a file: {rule_path}")
                continue
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    rule_contents.append({
                        'file': path.name,
                        'content': content
                    })
                    logger.info(f"Loaded rule file: {path.name}")
        except Exception as e:
            logger.error(f"Error loading rule file {rule_path}: {e}")
            continue
    
    if not rule_contents:
        logger.warning("No valid rule files loaded")
        return None
    
    # If only one rule file, return it directly
    if len(rule_contents) == 1:
        logger.info("Single rule file loaded, using content directly")
        return rule_contents[0]['content']
    
    # Multiple rule files - use LLM to summarize and consolidate
    logger.info(f"Summarizing {len(rule_contents)} rule files using LLM (blocking)")
    
    try:
        # Build prompt for summarization
        combined_rules = "\n\n---\n\n".join([
            f"## Rule File: {rule['file']}\n\n{rule['content']}"
            for rule in rule_contents
        ])
        
        summarization_prompt = f"""You are a code analysis expert. The user has provided multiple custom rule documents for analyzing their codebase.

Your task is to consolidate these rules into a single, coherent set of analysis guidelines.

REQUIREMENTS:
1. Preserve all important rules and guidelines from each document
2. Remove redundancy - if multiple documents mention the same rule, consolidate it
3. Organize rules logically by category (security, performance, style, etc.)
4. Keep the language clear and actionable
5. Maintain the priority and emphasis indicated in the original rules
6. Output should be concise but comprehensive

CUSTOM RULE DOCUMENTS:

{combined_rules}

OUTPUT FORMAT:
Provide a consolidated set of rules in markdown format. Use clear headings and bullet points. Be direct and specific."""

        # Configure Gemini
        if not config.use_local:
            import google.generativeai as genai
            
            genai.configure(api_key=config.google_api_key)
            model = genai.GenerativeModel(config.gemini_model)
            
            response = model.generate_content(
                summarization_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                )
            )
            
            summarized_rules = response.text.strip()
            logger.info("Successfully summarized custom rules")
            return summarized_rules
        else:
            # For local LLM (Ollama)
            import ollama
            
            response = ollama.generate(
                model=config.ollama_model,
                prompt=summarization_prompt,
                options={
                    'temperature': 0.3,
                    'num_predict': 4096,
                }
            )
            
            summarized_rules = response['response'].strip()
            logger.info("Successfully summarized custom rules using local LLM")
            return summarized_rules
            
    except Exception as e:
        logger.error(f"Error summarizing rules with LLM: {e}")
        logger.info("Falling back to concatenation of rule files")
        
        # Fallback: simple concatenation
        fallback_rules = "\n\n".join([
            f"# {rule['file']}\n\n{rule['content']}"
            for rule in rule_contents
        ])
        return fallback_rules
