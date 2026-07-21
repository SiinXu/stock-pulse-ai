# feishu_doc.py
# -*- coding: utf-8 -*-
import logging
import json
import lark_oapi as lark
from lark_oapi.api.docx.v1 import *
from typing import List, Dict, Any, Optional
from src.config import get_config
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class FeishuDocManager:
    """Feishu cloud document manager (based on the official SDK lark-oapi)"""

    def __init__(self):
        self.config = get_config()
        self.app_id = self.config.feishu_app_id
        self.app_secret = self.config.feishu_app_secret
        self.folder_token = self.config.feishu_folder_token

        # Initialize SDK client
        # SDK automatically handles tenant_access_token acquisition and refresh, without manual intervention
        if self.is_configured():
            self.client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .log_level(lark.LogLevel.INFO) \
                .build()
        else:
            self.client = None

    def is_configured(self) -> bool:
        """Check if the configuration is complete"""
        return bool(self.app_id and self.app_secret and self.folder_token)

    def create_daily_doc(self, title: str, content_md: str) -> Optional[str]:
        """
        Create daily report document
        """
        if not self.client or not self.is_configured():
            logger.warning("飞书 SDK 未初始化或配置缺失，跳过创建")
            return None

        try:
            # 1. Create document
            # Use the official SDK's Builder pattern to construct requests.
            create_request = CreateDocumentRequest.builder() \
                .request_body(CreateDocumentRequestBody.builder()
                              .folder_token(self.folder_token)
                              .title(title)
                              .build()) \
                .build()

            response = self.client.docx.v1.document.create(create_request)

            if not response.success():
                logger.error(f"创建文档失败: {response.code} - {response.msg} - {response.error}")
                return None

            doc_id = response.data.document.document_id
            # The domain here is just to generate links; actual access will be redirected.
            doc_url = f"https://feishu.cn/docx/{doc_id}"
            logger.info(f"飞书文档创建成功: {title} (ID: {doc_id})")

            # 2. Parse Markdown and write its content
            # Convert Markdown to a list of Block objects required by the SDK
            blocks = self._markdown_to_sdk_blocks(content_md)

            # Feishu API limit the number of blocks written each time (suggest 50 or less, write in batches)
            batch_size = 50
            doc_block_id = doc_id  # The document itself is also a block

            for i in range(0, len(blocks), batch_size):
                batch_blocks = blocks[i:i + batch_size]

                # Construct a request for batch adding blocks
                batch_add_request = CreateDocumentBlockChildrenRequest.builder() \
                    .document_id(doc_id) \
                    .block_id(doc_block_id) \
                    .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                                  .children(batch_blocks)  # SDK requires a Block object list
                                  .index(-1)  # Append to the end
                                  .build()) \
                    .build()

                write_resp = self.client.docx.v1.document_block_children.create(batch_add_request)

                if not write_resp.success():
                    logger.error(f"写入文档内容失败(批次{i}): {write_resp.code} - {write_resp.msg}")

            logger.info(f"文档内容写入完成")
            return doc_url

        except Exception as exc:
            log_safe_exception(
                logger,
                "Feishu document operation failed",
                exc,
                error_code="feishu_document_operation_failed",
            )
            return None

    def _markdown_to_sdk_blocks(self, md_text: str) -> List[Block]:
        """
        Convert simple Markdown to Feishu SDK Block object
        """
        blocks = []
        lines = md_text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Use plain text by default (Text = 2)
            block_type = 2
            text_content = line

            # Title recognition
            if line.startswith('# '):
                block_type = 3  # H1
                text_content = line[2:]
            elif line.startswith('## '):
                block_type = 4  # H2
                text_content = line[3:]
            elif line.startswith('### '):
                block_type = 5  # H3
                text_content = line[4:]
            elif line.startswith('---'):
                # Delimiter line
                blocks.append(Block.builder()
                              .block_type(22)
                              .divider(Divider.builder().build())
                              .build())
                continue

            # Construct a Block of type Text
            # SDK Structural nesting is very deep: Block -> Text -> elements -> TextElement -> TextRun -> content
            text_run = TextRun.builder() \
                .content(text_content) \
                .text_element_style(TextElementStyle.builder().build()) \
                .build()

            text_element = TextElement.builder() \
                .text_run(text_run) \
                .build()

            text_obj = Text.builder() \
                .elements([text_element]) \
                .style(TextStyle.builder().build()) \
                .build()

            # according to block_type Place the correct property container
            block_builder = Block.builder().block_type(block_type)

            if block_type == 2:
                block_builder.text(text_obj)
            elif block_type == 3:
                block_builder.heading1(text_obj)
            elif block_type == 4:
                block_builder.heading2(text_obj)
            elif block_type == 5:
                block_builder.heading3(text_obj)

            blocks.append(block_builder.build())

        return blocks
