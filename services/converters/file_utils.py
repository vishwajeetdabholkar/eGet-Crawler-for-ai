import os
import tempfile
from typing import List, Optional, Dict, Any
from loguru import logger
import base64
from PIL import Image
import io
import magic
import hashlib
from datetime import datetime
import mimetypes

class FileUtils:
    """Utility class for file operations"""
    
    @staticmethod
    def create_temp_file(content: bytes, suffix: str) -> str:
        """Create a temporary file with the given content and suffix"""
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            temp.write(content)
            temp.flush()
            return temp.name
        finally:
            temp.close()
    
    @staticmethod
    def cleanup_temp_files(files: List[str]) -> None:
        """Clean up temporary files"""
        for file_path in files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                logger.warning(f"Error cleaning up temp file {file_path}: {str(e)}")
    
    @staticmethod
    def encode_image(image_data: bytes, format: str = 'PNG', max_size_kb: int = 500) -> Optional[str]:
        """
        Encode image as base64, with optional format conversion and size limit
        Returns: base64 encoded image string or None if conversion fails
        """
        try:
            # Convert image format if needed
            img = Image.open(io.BytesIO(image_data))
            
            # Calculate target size if needed
            current_size = len(image_data) / 1024  # KB
            if current_size > max_size_kb:
                scale_factor = (max_size_kb / current_size) ** 0.5
                new_width = int(img.width * scale_factor)
                new_height = int(img.height * scale_factor)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to desired format
            output = io.BytesIO()
            
            if format.upper() == 'JPEG':
                # Convert RGBA to RGB if needed
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                img.save(output, format=format, quality=85, optimize=True)
            else:
                img.save(output, format=format, optimize=True)
            
            image_data = output.getvalue()
            encoded = base64.b64encode(image_data).decode('utf-8')
            mime_type = f"image/{format.lower()}"
            return f"data:{mime_type};base64,{encoded}"
            
        except Exception as e:
            logger.error(f"Image encoding error: {str(e)}")
            return None
    
    @staticmethod
    def get_file_metadata(file_path: str) -> Dict[str, Any]:
        """Get comprehensive file metadata"""
        try:
            stats = os.stat(file_path)
            mime = magic.Magic(mime=True)
            
            metadata = {
                'size_bytes': stats.st_size,
                'created': datetime.fromtimestamp(stats.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                'mime_type': mime.from_file(file_path),
                'extension': os.path.splitext(file_path)[1].lower(),
                'filename': os.path.basename(file_path)
            }
            
            # Calculate file hash
            with open(file_path, 'rb') as f:
                metadata['sha256'] = hashlib.sha256(f.read()).hexdigest()
            
            return metadata
        except Exception as e:
            logger.error(f"Error getting file metadata: {str(e)}")
            return {}
    
    @staticmethod
    def is_valid_image(image_data: bytes, allowed_formats: List[str] = None) -> bool:
        """
        Validate image data and optionally check format
        Args:
            image_data: Raw image bytes
            allowed_formats: List of allowed format extensions (e.g., ['jpg', 'png'])
        """
        try:
            img = Image.open(io.BytesIO(image_data))
            if allowed_formats:
                return img.format.lower() in [fmt.lower() for fmt in allowed_formats]
            return True
        except Exception:
            return False
    
    @staticmethod
    def normalize_filename(filename: str) -> str:
        """Normalize filename removing invalid characters"""
        # Remove invalid characters
        valid_chars = '-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        filename = ''.join(c for c in filename if c in valid_chars)
        
        # Ensure it's not empty
        filename = filename.strip() or 'unnamed_file'
        
        # Limit length
        max_length = 255
        name, ext = os.path.splitext(filename)
        if len(filename) > max_length:
            return name[:max_length-len(ext)] + ext
            
        return filename
    
    @staticmethod
    def get_safe_extension(filename: str) -> str:
        """Get safe file extension with fallback to mime type"""
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            mime_type = magic.from_file(filename, mime=True)
            ext = mimetypes.guess_extension(mime_type) or ''
        return ext.lstrip('.')
    
    @staticmethod
    def create_unique_temp_dir() -> str:
        """Create a unique temporary directory"""
        temp_dir = tempfile.mkdtemp()
        logger.debug(f"Created temporary directory: {temp_dir}")
        return temp_dir
    
    @staticmethod
    def get_file_encoding(file_path: str) -> str:
        """Detect file encoding"""
        try:
            import chardet
            with open(file_path, 'rb') as f:
                raw = f.read()
                result = chardet.detect(raw)
                return result['encoding'] or 'utf-8'
        except Exception as e:
            logger.warning(f"Error detecting file encoding: {str(e)}")
            return 'utf-8'  # Default to UTF-8
