#!/usr/bin/env python3
"""
F95Zone Game Crawler
Crawls game data from F95Zone forums and sends to WordPress via API
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
import sys
import os
from datetime import datetime
from urllib.parse import urljoin
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class F95ZoneCrawler:
    
    def __init__(self, config_file='config.json'):
        """Initialize crawler with configuration"""
        self.config = self.load_config(config_file)
        self.base_url = "https://f95zone.to"
        self.category_url = "https://f95zone.to/forums/games.2/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Add cookies for authentication if provided
        if 'cookies' in self.config:
            for cookie in self.config['cookies']:
                self.session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', 'f95zone.to'))
        
        # Cache for checking duplicates
        self.existing_thread_ids = self.get_existing_thread_ids()
        
    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Config file {config_file} not found")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            sys.exit(1)
    
    def get_existing_thread_ids(self):
        """Get list of existing thread IDs from WordPress to avoid duplicates"""
        try:
            api_url = self.config['wordpress_api_url'].replace('/create-post', '/existing-threads')
            headers = {'X-API-Key': self.config['wordpress_api_key']}

            # Fetch in pages to avoid very large single responses
            page_size = int(self.config.get('existing_page_size', 2000))
            offset = 0
            thread_ids = set()

            while True:
                params = {'limit': page_size, 'offset': offset}
                response = self.session.get(api_url, headers=headers, params=params, timeout=15)
                if response.status_code != 200:
                    logger.warning(f"Could not fetch existing thread IDs (status {response.status_code})")
                    break

                data = response.json()
                ids = data.get('thread_ids', [])
                for tid in ids:
                    thread_ids.add(str(tid))

                # If fewer than page_size returned, we're done
                if len(ids) < page_size:
                    break

                offset += page_size

            logger.info(f"Loaded {len(thread_ids)} existing thread IDs from WordPress")
            return thread_ids
        except Exception as e:
            logger.warning(f"Error fetching existing thread IDs: {e}")
            return set()
    
    def fetch_page(self, url, max_retries=3):
        """Fetch a page with retry logic"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to fetch {url} after {max_retries} attempts")
                    return None
    
    def parse_category_page(self, html):
        """Parse category page to extract thread links"""
        soup = BeautifulSoup(html, 'html.parser')
        threads = []
        
        # Thread IDs to always ignore (announcements, rules, etc.)
        IGNORE_THREAD_IDS = {'137266', '50885', '21333'}
        
        # Find all thread items
        thread_items = soup.find_all('div', class_='structItem--thread')
        
        for item in thread_items:
            try:
                # Extract thread link
                title_elem = item.find('a', {'data-tp-primary': 'on'})
                if not title_elem:
                    continue
                
                thread_url = urljoin(self.base_url, title_elem.get('href', ''))
                title = title_elem.text.strip()
                
                # Extract thread ID from URL
                thread_id_match = re.search(r'threads/[^/]+\.(\d+)', thread_url)
                thread_id = thread_id_match.group(1) if thread_id_match else None
                
                # Skip ignored threads
                if thread_id in IGNORE_THREAD_IDS:
                    logger.info(f"Skipping ignored thread: {title} (ID: {thread_id})")
                    continue
                
                # Extract author
                author_elem = item.find('a', class_='username')
                author = author_elem.text.strip() if author_elem else 'Unknown'
                author_url = urljoin(self.base_url, author_elem.get('href', '')) if author_elem else ''
                
                # Extract metadata
                meta_cell = item.find('div', class_='structItem-cell--meta')
                replies = 0
                views = 0
                
                if meta_cell:
                    pairs = meta_cell.find_all('dl', class_='pairs')
                    for pair in pairs:
                        dt = pair.find('dt')
                        dd = pair.find('dd')
                        if dt and dd:
                            if 'Replies' in dt.get('title', ''):
                                replies = int(dd.text.strip().replace(',', ''))
                            elif 'Views' in dt.get('title', ''):
                                views = int(dd.text.strip().replace(',', ''))
                
                # Extract rating
                rating_elem = item.find('span', class_='ratingStars')
                rating = 0
                rating_count = 0
                
                if rating_elem:
                    rating_title = rating_elem.get('title', '')
                    rating_match = re.search(r'([\d.]+)\s+star', rating_title)
                    if rating_match:
                        rating = float(rating_match.group(1))
                
                rating_text = item.find('span', class_='ratingStarsRow-text')
                if rating_text:
                    count_match = re.search(r'(\d+)', rating_text.text)
                    if count_match:
                        rating_count = int(count_match.group(1))
                
                # Extract prefixes (tags)
                prefixes = []
                prefix_elems = item.find_all('a', class_='labelLink')
                for prefix in prefix_elems:
                    prefixes.append(prefix.text.strip())
                
                threads.append({
                    'thread_id': thread_id,
                    'thread_url': thread_url,
                    'title': title,
                    'author': author,
                    'author_url': author_url,
                    'replies': replies,
                    'views': views,
                    'rating': rating,
                    'rating_count': rating_count,
                    'prefixes': prefixes
                })
                
            except Exception as e:
                logger.error(f"Error parsing thread item: {e}")
                continue
        
        return threads
    
    def parse_thread_page(self, html, thread_data):
        """Parse individual thread page to extract detailed game information"""
        soup = BeautifulSoup(html, 'html.parser')
        
        try:
            # Extract title from p-title-value
            title_elem = soup.find('h1', class_='p-title-value')
            if not title_elem:
                logger.warning("Could not find title")
                return None
            
            # Get full title text
            full_title = title_elem.get_text().strip()
            
            # Extract categories/prefixes (VN, Ren'Py, etc.)
            categories = []
            for label in title_elem.find_all('span', class_=['label', 'pre-renpy']):
                categories.append(label.get_text().strip())
            
            # Extract tags from js-tagList (separate from categories)
            tags = []
            tag_list = soup.find('span', class_='js-tagList')
            if tag_list:
                for tag_link in tag_list.find_all('a', class_='tagItem'):
                    tag_text = tag_link.get_text().strip()
                    if tag_text:
                        tags.append(tag_text)
            
            # Remove category labels from title to get clean game name
            clean_title = full_title
            for label in title_elem.find_all('span', class_=['label', 'pre-renpy']):
                clean_title = clean_title.replace(label.get_text().strip(), '').strip()
            
            # Extract version from title (pattern: [v1.0] or [1.0])
            version_match = re.search(r'\[v?([\d.]+[^\]]*)\]', clean_title)
            version = version_match.group(1) if version_match else ''
            
            # Extract developer from title (last brackets)
            developer_match = re.search(r'\[([^\]]+)\](?!.*\[)', clean_title)
            developer = developer_match.group(1) if developer_match and developer_match.group(1) != version else ''
            
            # Remove version and developer from title
            game_title = clean_title
            if version:
                game_title = game_title.replace(f'[v{version}]', '').replace(f'[{version}]', '')
            if developer:
                game_title = game_title.replace(f'[{developer}]', '')
            game_title = game_title.strip()
            
            # Find the first post (original post)
            first_post = soup.find('article', class_='message-body')
            if not first_post:
                logger.warning("Could not find first post content")
                return None
            
            # Extract content from bbWrapper
            content_div = first_post.find('div', class_='bbWrapper')
            if not content_div:
                logger.warning("Could not find content wrapper")
                return None
            
            # Parse content
            game_data = thread_data.copy()
            game_data['title'] = game_title
            game_data['version'] = version
            game_data['developer'] = developer
            
            # Extract OS/Platform information and add to categories
            content_text = content_div.get_text() if content_div else ''
            
            # Look for OS line in format "OS: Windows, Linux, Mac"
            os_match = re.search(r'OS[:\s]+([^\n]+)', content_text, re.IGNORECASE)
            if os_match:
                os_line = os_match.group(1).strip()
                # Split by comma and extract platform names
                platform_keywords = ['Windows', 'Linux', 'Mac', 'Android', 'iOS']
                for platform in platform_keywords:
                    if platform in os_line or platform.lower() in os_line.lower():
                        categories.append(platform)
            
            game_data['categories'] = categories
            game_data['tags'] = tags
            
            # Fix lazy-loaded images and remove duplicates in content before storing
            # Remove duplicate images (F95Zone has lazy-load duplicates)
            seen_images = set()
            images_to_remove = []
            
            for img in content_div.find_all('img', class_='bbImage'):
                # Get the actual image URL
                img_src = img.get('data-src') or img.get('src', '')
                
                # Mark duplicate for removal
                if img_src in seen_images:
                    images_to_remove.append(img)
                else:
                    seen_images.add(img_src)
                    
                    # Fix lazy-load: use data-src if available
                    data_src = img.get('data-src')
                    if data_src:
                        img['src'] = data_src
                        # Remove lazy-load attributes
                        img['class'] = [c for c in img.get('class', []) if c != 'lazyload']
                        if 'data-src' in img.attrs:
                            del img.attrs['data-src']
            
            # Remove duplicate images
            for img in images_to_remove:
                img.decompose()
            
            # Replace F95Zone image URLs with proxy URLs and remove /thumb/ for full resolution
            wordpress_url = self.config['wordpress_api_url'].replace('/wp-json/f95-crawler/v1/create-post', '')
            proxy_endpoint = f"{wordpress_url}/wp-json/f95-crawler/v1/image-proxy"
            
            import urllib.parse
            for img in content_div.find_all('img'):
                img_src = img.get('src', '')
                if 'attachments.f95zone.to' in img_src:
                    # Remove /thumb/ for full resolution images
                    full_res_url = img_src.replace('/thumb/', '/')
                    # Replace with proxy URL
                    proxied_url = f"{proxy_endpoint}?url={urllib.parse.quote(full_res_url)}"
                    img['src'] = proxied_url
            
            # Get the complete bbWrapper content as the body
            game_data['content'] = str(content_div)
            
            # Extract structured metadata from content text
            content_text = content_div.get_text()
            
            # Extract overview
            overview_match = re.search(r'Overview[:\s]+(.*?)(?=\n\n|Thread Updated|Release Date|Developer)', content_text, re.IGNORECASE | re.DOTALL)
            if overview_match:
                game_data['overview'] = overview_match.group(1).strip()
            
            # Extract metadata with improved patterns
            patterns = {
                'thread_updated': r'Thread Updated[:\s]+(\d{4}-\d{2}-\d{2})',
                'release_date': r'Release Date[:\s]+(\d{4}-\d{2}-\d{2})',
                'censored': r'Censored[:\s]+([^\n]+)',
                'os_platforms': r'OS[:\s]+([^\n]+)',
                'language': r'Language[:\s]+([^\n]+)',
                'genre': r'Genre[:\s]+([^\n]+)',
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, content_text, re.IGNORECASE)
                if match:
                    game_data[key] = match.group(1).strip()
            
            # Extract developer URL
            dev_tag = content_div.find('b', string=re.compile(r'Developer:', re.I))
            if dev_tag:
                dev_link = dev_tag.find_next('a')
                if dev_link:
                    game_data['developer_url'] = urljoin(self.base_url, dev_link.get('href', ''))
            
            # Extract genre (from spoiler or direct text)
            genre_tag = content_div.find('b', string=re.compile(r'Genre:', re.I))
            if genre_tag:
                genre_text = []
                for sibling in genre_tag.next_siblings:
                    if sibling.name == 'b':
                        break
                    if isinstance(sibling, str):
                        text = sibling.strip()
                        if text and text not in [':', '\n']:
                            genre_text.append(text)
                    elif sibling.name == 'br':
                        break
                game_data['genre'] = ' '.join(genre_text).strip()
            
            # Extract changelog
            changelog_tag = content_div.find('b', string=re.compile(r'Changelog:', re.I))
            if changelog_tag:
                changelog_spoiler = changelog_tag.find_next('div', class_='bbCodeSpoiler')
                if changelog_spoiler:
                    game_data['changelog'] = changelog_spoiler.get_text().strip()
            
            # Extract installation instructions
            install_tag = content_div.find('b', string=re.compile(r'Installation:', re.I))
            if install_tag:
                install_spoiler = install_tag.find_next('div', class_='bbCodeSpoiler')
                if install_spoiler:
                    game_data['installation'] = install_spoiler.get_text().strip()
            
            # Extract download links - improved filtering
            download_links = []
            
            # Find DOWNLOAD text (can be in span or b tag)
            download_markers = content_div.find_all(string=re.compile(r'DOWNLOAD', re.I))
            
            if download_markers:
                # Look for actual download links (common hosting sites)
                hosting_patterns = [
                    'mega.nz', 'pixeldrain', 'gofile', 'anonfiles', 'workupload',
                    'mediafire', 'uploadhaven', 'mixdrop', 'krakenfiles', 'dropbox',
                    'drive.google', 'nopy.to', 'wetransfer', 'sendspace', 'buzzheavier',
                    'uploadnow', 'f95zone.to/masked', 'catbox.moe', 'datanodes.to'
                ]
                
                # Get the parent container of the first download marker
                download_marker = download_markers[0]
                parent = download_marker.find_parent()
                
                while parent and parent.name != 'div':
                    parent = parent.find_parent()
                
                if parent:
                    # Get text context for finding platform info
                    parent_text = parent.get_text()
                    
                    # Find all links in the download section
                    for link in parent.find_all('a'):
                        href = link.get('href', '')
                        
                        # Check if this link points to a file hosting site
                        if href and any(host in href.lower() for host in hosting_patterns):
                            text = link.get_text().strip()
                            
                            # Skip empty or very short text
                            if not text or len(text) < 2:
                                continue
                            
                            # Skip common UI/navigation elements
                            if text.upper() in ['REACTIONS', 'MEMBERS', 'LOGIN', 'REGISTER', 'FORUMS', 'TAGS']:
                                continue
                            
                            # Try to find platform info nearby
                            platform = ''
                            # Check siblings and parents for platform indicators
                            for sibling in [link.find_previous_sibling(), link.parent]:
                                if sibling and hasattr(sibling, 'get_text'):
                                    sib_text = sibling.get_text()
                                    if 'Win' in sib_text or 'Mac' in sib_text or 'Linux' in sib_text or 'Android' in sib_text:
                                        platform = sib_text.strip()
                                        break
                            
                            download_links.append({
                                'platform': platform,
                                'host': text.upper(),
                                'url': href
                            })
            
            game_data['download_links'] = download_links
            
            # Extract first image from bbWrapper as featured image
            # Skip lazy-load placeholders (data:image/svg+xml)
            first_img = None
            for img in content_div.find_all('img', class_='bbImage'):
                img_src = img.get('src', '')
                # Check data-src first (lazy load), then src
                if not img_src or 'data:image' in img_src or 'svg+xml' in img_src:
                    img_src = img.get('data-src', '')
                
                if img_src and 'http' in img_src:
                    first_img = img
                    break
            
            if first_img:
                img_src = first_img.get('data-src') or first_img.get('src', '')
                if img_src and 'http' in img_src:
                    # Get full size image URL
                    full_img = img_src.replace('/thumb/', '/')
                    game_data['featured_image'] = full_img
                    game_data['use_external_images'] = True
            
            # Extract all images (skip placeholders and duplicates)
            images = []
            seen_images = set()
            for img in content_div.find_all('img', class_='bbImage'):
                img_src = img.get('src', '')
                # Check data-src first (lazy load), then src
                if not img_src or 'data:image' in img_src or 'svg+xml' in img_src:
                    img_src = img.get('data-src', '')
                
                if img_src and 'http' in img_src:
                    full_img = img_src.replace('/thumb/', '/')
                    # Only add if not already seen
                    if full_img not in seen_images:
                        images.append(full_img)
                        seen_images.add(full_img)
            
            game_data['images'] = images
            
            return game_data
            
        except Exception as e:
            logger.error(f"Error parsing thread page: {e}")
            return None
    
    def send_to_wordpress(self, game_data):
        """Send game data to WordPress via REST API"""
        api_url = self.config['wordpress_api_url']
        api_key = self.config['wordpress_api_key']
        
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': api_key
        }
        
        try:
            response = requests.post(api_url, json=game_data, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Successfully sent: {game_data['title']} - Post ID: {result.get('post_id')}")
            
            # Add to cache
            if game_data.get('thread_id'):
                self.existing_thread_ids.add(game_data['thread_id'])
            
            return result
            
        except requests.RequestException as e:
            logger.error(f"Failed to send to WordPress: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
    
    def send_batch_to_wordpress(self, batch_data):
        """Send multiple games to WordPress in one request"""
        api_url = self.config['wordpress_api_url'].replace('/create-post', '/create-batch')
        api_key = self.config['wordpress_api_key']
        
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': api_key
        }
        
        try:
            response = requests.post(api_url, json={'posts': batch_data}, headers=headers, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            created = result.get('created', 0)
            skipped = result.get('skipped', 0)
            
            logger.info(f"Batch sent: {created} created, {skipped} skipped")
            
            # Add to cache
            for game in batch_data:
                if game.get('thread_id'):
                    self.existing_thread_ids.add(game['thread_id'])
            
            return result
            
        except requests.RequestException as e:
            logger.warning(f"Batch send failed, falling back to individual sends: {e}")
            # Fallback to individual sends
            success = 0
            for game_data in batch_data:
                if self.send_to_wordpress(game_data):
                    success += 1
            return {'created': success, 'skipped': 0}
    
    def crawl_category(self, max_pages=1, start_page=1):
        """Crawl category pages and extract thread listings"""
        all_threads = []
        
        for page in range(start_page, start_page + max_pages):
            page_url = f"{self.category_url}page-{page}" if page > 1 else self.category_url
            logger.info(f"Fetching category page {page}: {page_url}")
            
            html = self.fetch_page(page_url)
            if not html:
                logger.warning(f"Skipping page {page} due to fetch error")
                continue
            
            threads = self.parse_category_page(html)
            logger.info(f"Found {len(threads)} threads on page {page}")
            all_threads.extend(threads)
            
            # Be respectful to the server
            time.sleep(self.config.get('delay_between_requests', 2))
        
        return all_threads
    
    def crawl_threads(self, threads, max_threads=None, batch_size=5):
        """Crawl individual thread pages with batch processing"""
        if max_threads:
            threads = threads[:max_threads]
        
        # Filter out already existing threads
        threads_to_process = []
        skipped_count = 0
        
        for thread in threads:
            if thread['thread_id'] in self.existing_thread_ids:
                logger.info(f"Skipping duplicate: {thread['title']} (ID: {thread['thread_id']})")
                skipped_count += 1
            else:
                threads_to_process.append(thread)
        
        logger.info(f"Skipped {skipped_count} duplicates, processing {len(threads_to_process)} new threads")
        
        total = len(threads_to_process)
        success_count = 0
        failed_threads = []
        
        # Process in batches
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = threads_to_process[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_start//batch_size + 1} ({batch_start + 1}-{batch_end}/{total})")
            
            batch_data = []
            
            for idx, thread in enumerate(batch, batch_start + 1):
                logger.info(f"Processing thread {idx}/{total}: {thread['title']}")
                
                html = self.fetch_page(thread['thread_url'])
                if not html:
                    logger.warning(f"Skipping thread: {thread['title']}")
                    failed_threads.append(thread['title'])
                    continue
                
                game_data = self.parse_thread_page(html, thread)
                if not game_data:
                    logger.warning(f"Failed to parse thread: {thread['title']}")
                    failed_threads.append(thread['title'])
                    continue
                
                batch_data.append(game_data)
                
                # Be respectful to the server
                time.sleep(self.config.get('delay_between_requests', 2))
            
            # Send batch to WordPress
            if batch_data:
                result = self.send_batch_to_wordpress(batch_data)
                if result:
                    success_count += len(batch_data)
            
            logger.info(f"Batch complete: {success_count}/{total} threads processed successfully")
        
        if failed_threads:
            logger.warning(f"Failed threads: {', '.join(failed_threads[:10])}")
        
        logger.info(f"Completed: {success_count}/{total} threads successfully processed")
        return success_count
    
    def run(self, max_pages=1, max_threads=None, batch_size=5):
        """Main execution method"""
        logger.info("Starting F95Zone crawler")
        logger.info(f"Crawling {max_pages} category page(s)")
        logger.info(f"Batch processing: {batch_size} threads per batch")
        
        # Crawl category pages
        threads = self.crawl_category(max_pages=max_pages)
        logger.info(f"Total threads found: {len(threads)}")
        
        if not threads:
            logger.warning("No threads found, exiting")
            return
        
        # Crawl individual threads with batch processing
        self.crawl_threads(threads, max_threads=max_threads, batch_size=batch_size)
        
        logger.info("Crawler completed")


def main():
    """Main entry point"""
    import argparse
    import os
    
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(script_dir, 'config.json')
    
    parser = argparse.ArgumentParser(description='F95Zone Game Crawler')
    parser.add_argument('--config', default=default_config, help='Config file path')
    parser.add_argument('--pages', type=int, help='Number of category pages to crawl (default: infinite)')
    parser.add_argument('--max-threads', type=int, help='Maximum number of threads to process (default: all)')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for processing (default: 10)')
    parser.add_argument('--infinite', action='store_true', help='Run continuously, crawling all pages')
    
    args = parser.parse_args()
    
    # Default to infinite crawling if no pages specified
    pages = args.pages if args.pages else (999999 if args.infinite or args.pages is None else 1)
    
    crawler = F95ZoneCrawler(config_file=args.config)
    crawler.run(max_pages=pages, max_threads=args.max_threads, batch_size=args.batch_size)


if __name__ == '__main__':
    main()
