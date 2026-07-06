"""
PDF Text Extractor
"""
import asyncio
from typing import Dict, List
import pdfplumber


class PDFProcessor:
    """Extract text from PDF files"""

    def extract_text(self, file_path: str) -> str:
        """Extract all text from PDF"""
        text_parts = []

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    text_parts.append(f"--- Page {page_num} ---\n{text}")

        return "\n\n".join(text_parts)

    async def extract_text_async(self, file_path: str) -> str:
        """Extract all text from PDF asynchronously"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.extract_text, file_path
        )

    def extract_pages(self, file_path: str) -> List[Dict]:
        """Extract text page by page with metadata"""
        pages = []

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    pages.append({
                        "page_number": page_num,
                        "text": text.strip(),
                        "word_count": len(text.split())
                    })

        return pages

    async def extract_pages_async(self, file_path: str) -> List[Dict]:
        """Extract pages asynchronously"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.extract_pages, file_path
        )

    def extract_with_metadata(self, file_path: str) -> Dict:
        """Extract text with PDF metadata"""
        result = {
            "text": "",
            "pages": [],
            "metadata": {}
        }

        with pdfplumber.open(file_path) as pdf:
            # Get metadata
            result["metadata"] = {
                "page_count": len(pdf.pages),
                "metadata": pdf.metadata
            }

            # Extract pages
            pages = self.extract_pages(file_path)
            result["pages"] = pages
            result["text"] = "\n\n".join([p["text"] for p in pages])

        return result

    async def extract_with_metadata_async(self, file_path: str) -> Dict:
        """Extract with metadata asynchronously"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.extract_with_metadata, file_path
        )


async def process_pdf(file_path: str) -> str:
    """Process PDF file and return text"""
    processor = PDFProcessor()
    return await processor.extract_with_metadata_async(file_path)
