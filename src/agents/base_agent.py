"""Base agent class using LangChain with Gemini"""

import json
import logging
import asyncio
import uuid
import time
from typing import Dict, Any, List, Optional, Type, TypeVar, Callable
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from pydantic import BaseModel

from ..core.config import AgentConfig, RedisConfig
from ..core.redis_client import RedisClient, get_redis_client
from ..core.message_history import MessageHistoryManager, MessageRole

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class BaseAgent:
    """Base agent class using LangChain with Gemini"""
    
    def __init__(self, config: AgentConfig, redis_config: Optional[RedisConfig] = None):
        self.config = config
        self.redis_config = redis_config
        self.cache = {}  # Fallback in-memory cache
        self.max_cache_size = 100
        
        # Redis components
        self.redis_client: Optional[RedisClient] = None
        self.message_history_manager: Optional[MessageHistoryManager] = None
        
        # Initialize LLM based on configuration
        if config.use_local:
            # Initialize Ollama for local LLM
            self.llm = ChatOllama(
                model=config.ollama_model,
                temperature=config.temperature,
                num_predict=config.max_tokens
            )
        else:
            # Initialize Gemini (default cloud LLM)
            self.llm = ChatGoogleGenerativeAI(
                model=config.gemini_model,
                google_api_key=config.google_api_key,
                temperature=config.temperature,
                max_output_tokens=config.max_tokens
            )

        
        # Create prompt template
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template("{system_prompt}"),
            HumanMessagePromptTemplate.from_template("{user_prompt}")
        ])
    
    @property
    def system_prompt(self) -> str:
        """System prompt for the agent - to be overridden by subclasses"""
        return "You are a helpful AI assistant."
    
    @property
    def agent_name(self) -> str:
        """Agent name - to be overridden by subclasses"""
        return "base_agent"
    
    async def initialize_redis(self) -> bool:
        """Initialize Redis connection and message history manager"""
        if not self.redis_config:
            logger.warning("Redis config not provided, using in-memory cache only")
            return False
        
        try:
            self.redis_client = await get_redis_client(self.redis_config)
            self.message_history_manager = MessageHistoryManager(self.redis_client, self.redis_config)
            print("Redis initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            return False
    
    def _generate_cache_key(self, prompt: str, context: Dict[str, Any]) -> str:
        """Generate a cache key for the prompt and context"""
        context_str = json.dumps(context, sort_keys=True) if context else ""
        return f"{self.agent_name}_{hash(prompt + context_str)}"
    
    async def _get_from_cache(self, cache_key: str) -> Optional[str]:
        """Get response from cache"""
        # Try Redis first
        if self.redis_client:
            try:
                cached_value = await self.redis_client.get_cache(cache_key)
                if cached_value:
                    return cached_value
            except Exception as e:
                logger.warning(f"Redis cache get failed: {e}")
        
        # Fallback to in-memory cache
        return self.cache.get(cache_key)
    
    async def _add_to_cache(self, cache_key: str, response: str):
        """Add response to cache"""
        # Try Redis first
        if self.redis_client:
            try:
                await self.redis_client.set_cache(cache_key, response)
                return
            except Exception as e:
                logger.warning(f"Redis cache set failed: {e}")
        
        # Fallback to in-memory cache
        if len(self.cache) >= self.max_cache_size:
            # Remove oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[cache_key] = response
    
    def _build_prompt(self, user_prompt: str, context: Dict[str, Any] = None) -> str:
        """Build the full prompt with context"""
        context = context or {}
        
        # Add context to the prompt
        if context:
            context_str = "\n".join([f"- {k}: {v}" for k, v in context.items()])
            user_prompt = f"Context:\n{context_str}\n\n{user_prompt}"
        
        return user_prompt
    
    async def generate_response(self, prompt: str, context: Dict[str, Any] = None) -> str:
        """Generate a response using LangChain"""
        context = context or {}
        
        # Check cache
        cache_key = self._generate_cache_key(prompt, context)
        cached_response = await self._get_from_cache(cache_key)
        if cached_response:
            print(f"Using cached response for {self.agent_name}")
            return cached_response
        
        try:
            # Build the full prompt
            full_prompt = self._build_prompt(prompt, context)
            
            # Create messages
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=full_prompt)
            ]
            
            # Generate response with timing
            start_time = time.time()
            print(f"[LLM DEBUG] {self.agent_name} - Invoking LLM for generate_response")
            logger.debug(f"[LLM DEBUG] Prompt preview (first 500 chars): {full_prompt[:500]}...")
            
            response = await self.llm.ainvoke(messages)
            
            elapsed_time = time.time() - start_time
            print(f"[LLM DEBUG] {self.agent_name} - LLM response received in {elapsed_time:.2f}s")
            
            # Extract content
            response_text = response.content if hasattr(response, 'content') else str(response)
            print(f"[LLM DEBUG] Response preview: {response_text}")
            
            # Cache the response
            await self._add_to_cache(cache_key, response_text)
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise
    
    async def generate_structured_response(self, prompt: str, 
                                         response_schema: Type[T],
                                         context: Dict[str, Any] = None) -> T:
        """Generate a structured response using Pydantic output parser"""
        context = context or {}
        
        # Check cache
        cache_key = self._generate_cache_key(f"structured_{prompt}", context)
        cached_response = await self._get_from_cache(cache_key)
        if cached_response:
            try:
                return response_schema.model_validate_json(cached_response)
            except Exception:
                # If cached response can't be parsed, continue with fresh generation
                pass
        
        try:
            # Build the full prompt
            full_prompt = self._build_prompt(prompt, context)
            
            # Create output parser
            parser = PydanticOutputParser(pydantic_object=response_schema)
            
            # Add format instructions to the prompt
            format_instructions = parser.get_format_instructions()
            full_prompt = f"{full_prompt}\n\n{format_instructions}"
            
            # Create messages
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=full_prompt)
            ]
            
            # Generate response with timing
            start_time = time.time()
            print(f"[LLM DEBUG] {self.agent_name} - Invoking LLM for generate_structured_response")
            logger.debug(f"[LLM DEBUG] Prompt preview (first 500 chars): {full_prompt[:500]}...")
            print(f"[LLM DEBUG] Response schema: {response_schema.__name__}")
            
            response = await self.llm.ainvoke(messages)
            
            elapsed_time = time.time() - start_time
            print(f"[LLM DEBUG] {self.agent_name} - LLM response received in {elapsed_time:.2f}s")
            
            # Extract content
            response_text = response.content if hasattr(response, 'content') else str(response)
            print(f"[LLM DEBUG] Response preview: {response_text}")
            
            # Parse the structured response
            try:
                # Check if response is empty or whitespace only
                if not response_text or not response_text.strip():
                    logger.warning("Received empty response from LLM")
                    # Return a default empty response
                    return response_schema.model_validate({"issues": []})
                
                result = parser.parse(response_text)
                # Cache the JSON string
                await self._add_to_cache(cache_key, response_text)
                return result
            except Exception as parse_error:
                logger.warning(f"Failed to parse structured response: {parse_error}")
                # Try to extract JSON from the response
                try:
                    # Look for JSON in the response
                    import re
                    
                    # First try to extract JSON from markdown code blocks
                    json_pattern = r'```(?:json)?\s*(\{.*\})\s*```'
                    json_match = re.search(json_pattern, response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                        result = response_schema.model_validate_json(json_str)
                        await self._add_to_cache(cache_key, json_str)
                        return result
                    
                    # If no markdown blocks, try to find JSON directly
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group()
                        result = response_schema.model_validate_json(json_str)
                        await self._add_to_cache(cache_key, json_str)
                        return result
                except Exception as e:
                    logger.warning(f"Failed to extract JSON from response: {e}")
                    pass
                
                # If all parsing fails, return a schema-appropriate default instead of raising
                logger.error(f"All JSON parsing attempts failed, returning empty response. Original error: {parse_error}")
                try:
                    # Prefer defaults based on known fields
                    if 'issues' in response_schema.model_fields:
                        return response_schema.model_validate({"issues": []})
                    if 'answer' in response_schema.model_fields:
                        return response_schema.model_validate({"answer": "", "files_to_analyze": [], "analysis_complete": False})
                except Exception:
                    pass
                # Last resort: construct with no data
                return response_schema.model_validate({})
            
        except Exception as e:
            logger.error(f"Error generating structured response: {e}")
            raise
    
    async def generate_structured_response_with_functions(self, prompt: str, 
                                                        response_schema: Type[T],
                                                        function_declarations: List[BaseModel],
                                                        function_handlers: Dict[str, Callable],
                                                        context: Dict[str, Any] = None) -> T:
        """Generate a structured response with function calling support"""
        context = context or {}
        
        # Check cache
        cache_key = self._generate_cache_key(f"structured_functions_{prompt}", context)
        cached_response = await self._get_from_cache(cache_key)
        if cached_response:
            try:
                return response_schema.model_validate_json(cached_response)
            except Exception:
                pass
        
        try:
            # Build the full prompt
            full_prompt = self._build_prompt(prompt, context)
            
            # Bind tools to the LLM
            llm_with_tools = self.llm.bind_tools(function_declarations)
            
            # Create initial messages
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=full_prompt)
            ]
            
            # First invocation with tools
            start_time = time.time()
            print(f"[LLM DEBUG] {self.agent_name} - Invoking LLM with function tools")
            print(f"[LLM DEBUG] Prompt preview: {full_prompt}...")
            response = await llm_with_tools.ainvoke(messages)
            
            elapsed_time = time.time() - start_time
            print(f"[LLM DEBUG] {self.agent_name} - Initial LLM response with tools received in {elapsed_time:.2f}s, response: {response}")
            
            # Check if the response contains tool calls
            if hasattr(response, 'tool_calls') and response.tool_calls:
                print(f"Tool calls detected: {[call['name'] for call in response.tool_calls]}")
                
                # Execute tool calls
                tool_messages = []
                for tool_call in response.tool_calls:
                    function_name = tool_call['name']
                    function_args = tool_call.get('args', {})
                    
                    if function_name in function_handlers:
                        try:
                            result = await function_handlers[function_name](**function_args)
                            
                            # Ensure result is serializable
                            if isinstance(result, (dict, list)):
                                result_content = json.dumps(result)
                            else:
                                result_content = str(result)
                            
                            tool_messages.append(ToolMessage(
                                content=result_content,
                                tool_call_id=tool_call['id']
                            ))
                            print(f"Function {function_name} executed successfully with result: {result_content}")
                            
                        except Exception as e:
                            logger.error(f"Error executing function {function_name}: {e}")
                            tool_messages.append(ToolMessage(
                                content=f"Error: {str(e)}",
                                tool_call_id=tool_call['id']
                            ))
                    else:
                        logger.warning(f"No handler found for function: {function_name}")
                        tool_messages.append(ToolMessage(
                            content=f"Error: No handler found for function: {function_name}",
                            tool_call_id=tool_call['id']
                        ))
                
                # Add tool messages to conversation
                messages.extend([response] + tool_messages)
                
                # Add a clear instruction for structured output
                schema_name = response_schema.__name__
                final_prompt = f"""Based on the function execution results above, provide your final response as a {schema_name}. 
                
                Important: 
                - Do NOT make any more function calls
                - Provide ONLY the structured response with the required fields
                - For AnalysisResponseSchema: provide 'issues' (list, required) and optionally 'summary' (dict or null)
                - For ChatResponseSchema: provide 'answer' (string), 'files_to_analyze' (list), and 'analysis_complete' (boolean)"""
                
                messages.append(HumanMessage(content=final_prompt))
                
                # Use with_structured_output for the final response
                start_time = time.time()
                print(f"[LLM DEBUG] {self.agent_name} - Invoking LLM for final structured response after tool execution")
                
                structured_llm = self.llm.with_structured_output(response_schema)
                final_result = await structured_llm.ainvoke(messages)
                
                elapsed_time = time.time() - start_time
                print(f"[LLM DEBUG] {self.agent_name} - Final structured response received in {elapsed_time:.2f}s")
                print(f"[LLM DEBUG] Final result: {final_result}")
                
                # Cache the result
                await self._add_to_cache(cache_key, final_result.model_dump_json())
                return final_result
                
            else:
                # No tool calls detected - still need to get structured response
                print("No tool calls detected in response, requesting structured output")
                
                # Add the AI response to messages
                messages.append(response)
                
                # Add instruction for structured output
                schema_name = response_schema.__name__
                final_prompt = f"""Please provide your response as a {schema_name} in the required structured format. 
                
                Important: 
                - Provide ONLY the structured response with the required fields
                - For AnalysisResponseSchema: provide 'issues' (list, required) and optionally 'summary' (dict or null)
                - For ChatResponseSchema: provide 'answer' (string), 'files_to_analyze' (list), and 'analysis_complete' (boolean)"""
                
                messages.append(HumanMessage(content=final_prompt))
                
                # Get structured response
                structured_llm = self.llm.with_structured_output(response_schema)
                final_result = await structured_llm.ainvoke(messages)

                print(f"[LLM DEBUG] {self.agent_name} - Final structured response received in {elapsed_time:.2f}s, response: {final_result}")
                
                # Cache the result
                await self._add_to_cache(cache_key, final_result.model_dump_json())
                return final_result
            
        except Exception as e:
            logger.error(f"Error generating structured response with functions: {e}")
            raise

    
    def parse_json_response(self, response: str) -> Any:
        """Parse JSON response, handling various formats"""
        try:
            # Try direct JSON parsing first
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            
            # Look for JSON in code blocks
            json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
            matches = re.findall(json_pattern, response, re.DOTALL)
            
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
            
            # Look for JSON anywhere in the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            # If all else fails, try to parse as a list
            list_match = re.search(r'\[.*\]', response, re.DOTALL)
            if list_match:
                try:
                    return json.loads(list_match.group())
                except json.JSONDecodeError:
                    pass
            
            raise ValueError(f"Could not parse JSON from response: {response[:200]}...")
    
    def format_code_snippet(self, code: str, language: str = "text") -> str:
        """Format code snippet for display"""
        return f"```{language}\n{code}\n```"