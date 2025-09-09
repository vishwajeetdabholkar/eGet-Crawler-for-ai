from bs4 import BeautifulSoup
import json
from typing import Dict, List, Optional, Any
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from .validators import StructuredDataValidator

class StructuredDataExtractor:
    """Extract structured data from web pages"""
    
    def _extract_language(self, soup: BeautifulSoup) -> Optional[str]:
        """Enhanced language extraction with better fallbacks"""
        try:
            # Try html lang attribute first
            html_tag = soup.find('html')
            if html_tag and html_tag.get('lang'):
                return html_tag.get('lang').split('-')[0]  # Get primary language code
            
            # Try various meta tags
            meta_lang_selectors = [
                {'attrs': {'http-equiv': 'content-language'}},
                {'attrs': {'name': 'language'}},
                {'attrs': {'property': 'og:locale'}}
            ]
            
            for selector in meta_lang_selectors:
                meta_tag = soup.find('meta', **selector)
                if meta_tag and meta_tag.get('content'):
                    lang = meta_tag.get('content').split('_')[0]
                    if lang:
                        return lang
            
            # If no language found, return empty string instead of None
            return ''
            
        except Exception as e:
            logger.warning(f"Language extraction failed: {str(e)}")
            return ''  # Return empty string on error

    def extract_json_ld(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract JSON-LD data from script tags"""
        json_ld_data = []
        try:
            script_tags = soup.find_all('script', type='application/ld+json')
            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    json_ld_data.append(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON-LD: {e}")
        except Exception as e:
            logger.error(f"Error extracting JSON-LD: {e}")
        return json_ld_data

    def extract_open_graph(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract OpenGraph metadata"""
        og_data = {}
        try:
            og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
            for tag in og_tags:
                property_name = tag.get('property', '').replace('og:', '')
                content = tag.get('content')
                if property_name and content:
                    og_data[property_name] = content
        except Exception as e:
            logger.error(f"Error extracting OpenGraph data: {e}")
        return og_data

    def extract_twitter_cards(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Twitter Card metadata"""
        twitter_data = {}
        try:
            twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
            for tag in twitter_tags:
                property_name = tag.get('name', '').replace('twitter:', '')
                content = tag.get('content')
                if property_name and content:
                    twitter_data[property_name] = content
        except Exception as e:
            logger.error(f"Error extracting Twitter Card data: {e}")
        return twitter_data

    def extract_meta_data(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract standard meta tags"""
        meta_data = {}
        try:
            meta_tags = soup.find_all('meta')
            for tag in meta_tags:
                name = tag.get('name') or tag.get('property')
                content = tag.get('content')
                if name and content and not name.startswith(('og:', 'twitter:')):
                    meta_data[name] = content
            
            # Set language, defaulting to empty string if not found
            meta_data['language'] = self._extract_language(soup) or ''
                
        except Exception as e:
            logger.error(f"Error extracting meta data: {e}")
            meta_data['language'] = ''  # Ensure language field exists with empty string
            
        return meta_data

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def extract_all(self, html: str) -> Dict[str, Any]:
        """Extract and validate all structured data from HTML with optimized parsing"""
        try:
            # Use lxml parser for better performance, fallback to html.parser
            try:
                soup = BeautifulSoup(html, 'lxml')
            except Exception:
                soup = BeautifulSoup(html, 'html.parser')
            
            data = {
                'jsonLd': self.extract_json_ld(soup),
                'openGraph': self.extract_open_graph(soup),
                'twitterCard': self.extract_twitter_cards(soup),
                'metaData': self.extract_meta_data(soup)
            }
            
            # Ensure metaData exists and has required fields
            if 'metaData' not in data:
                data['metaData'] = {}
            if 'language' not in data['metaData']:
                data['metaData']['language'] = ''
            
            try:
                validated_data = StructuredDataValidator(**data).dict(exclude_none=True)
                return validated_data
            except Exception as validation_error:
                logger.warning(f"Validation error: {str(validation_error)}")
                # Return basic structure with empty string for language
                return {
                    'jsonLd': [],
                    'openGraph': {},
                    'twitterCard': {},
                    'metaData': {'language': ''}
                }
                
        except Exception as e:
            logger.error(f"Error in structured data extraction: {e}")
            # Return basic structure with empty string for language
            return {
                'jsonLd': [],
                'openGraph': {},
                'twitterCard': {},
                'metaData': {'language': ''}
            }