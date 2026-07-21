# -*- coding: utf-8 -*-
"""
===================================
Platform adapter base class
===================================

Define the abstract base class of platform adapters. Each platform must inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

from bot.models import BotMessage, BotResponse, WebhookResponse


class BotPlatform(ABC):
    """
    Platform adapter abstract base class
    
    Responsible for:
    1. Validate Webhook request signature
    2. Parse platform messages into a unified format
    3. Convert responses to platform format
    
    Using example:
        class MyPlatform(BotPlatform):
            @property
            def platform_name(self) -> str:
                return "myplatform"
            
            def verify_request(self, headers, body) -> bool:
                # Validate signature logic
                return True
            
            def parse_message(self, data) -> Optional[BotMessage]:
                # Parse message logic
                return BotMessage(...)
            
            def format_response(self, response, message) -> WebhookResponse:
                # Format the response logic
                return WebhookResponse.success({"text": response.text})
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        Platform identifier name
        
        Used for route matching and log identification, such as "feishu", "dingtalk".
        """
        pass
    
    @abstractmethod
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """
        Verification Request Signature
        
        Each platform has a different signature verification mechanism and needs to be implemented separately.
        
        Args:
            headers: HTTP request headers
            body: Raw bytes of the request body
            
        Returns:
            Signature validity check
        """
        pass
    
    @abstractmethod
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """
        Parse platform messages into a unified format
        
        Convert platform-specific message formats to BotMessage.
        If not the message type to be processed (e.g., event callback), return None.
        
        Args:
            data: Parsed JSON data
            
        Returns:
            BotMessage object, or None (no need to handle)
        """
        pass
    
    @abstractmethod
    def format_response(
        self, 
        response: BotResponse, 
        message: BotMessage
    ) -> WebhookResponse:
        """
        Convert unified responses to platform format
        
        Args:
            response: unified response object
            message: Original message object (used to obtain reply target information)
            
        Returns:
            WebhookResponse object
        """
        pass
    
    def send_followup(
        self,
        response: 'BotResponse',
        message: 'BotMessage',
    ) -> bool:
        """Send a follow-up message after a deferred webhook response.

        Override in platforms that return a deferred acknowledgement
        (e.g. Discord type 5) so the final command result can be delivered
        asynchronously.  The default implementation is a no-op.

        Returns:
            ``True`` if the follow-up was sent successfully.
        """
        return False

    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """
        Process platform verification requests
        
        Some platforms send verification requests when configuring Webhooks, requiring a specific response to be returned.
        Subclasses can override this method.
        
        Args:
            data: Request data
            
        Returns:
            Validate response, or None (not a validation request)
        """
        return None
    
    def handle_webhook(
        self, 
        headers: Dict[str, str], 
        body: bytes,
        data: Dict[str, Any]
    ) -> Tuple[Optional[BotMessage], Optional[WebhookResponse]]:
        """
        Handle webhook requests
        
        This is the main entry method, coordinating verification and parsing processes.
        
        Args:
            headers: HTTP request headers
            body: Raw bytes of the request body
            data: Parsed JSON data
            
        Returns:
            (BotMessage, WebhookResponse) Tuple
            - If it's a validation request: (None, challenge_response)
            - If it's a normal message: (message, None) - The response will be generated after command processing
            - If verification fails or no processing is required: (None, error_response or None)
        """
        # 1. Check if it's a validation request.
        challenge_response = self.handle_challenge(data)
        if challenge_response:
            return None, challenge_response
        
        # 2. Verification Request Signature
        if not self.verify_request(headers, body):
            return None, WebhookResponse.error("Invalid signature", 403)
        
        # 3. Parse message
        message = self.parse_message(data)
        
        return message, None
