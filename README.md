# F95Zone WordPress Crawler

Automated crawler for F95Zone game threads that creates WordPress posts via REST API.

## Features

- ✅ Crawls game threads from F95Zone
- ✅ Extracts game metadata (title, version, developer, tags, categories, OS platforms)
- ✅ Processes images with proxy to bypass hotlink protection
- ✅ Batch processing for efficiency
- ✅ Duplicate detection
- ✅ Runs on GitHub Actions (scheduled every 6 hours)

## Setup

### 1. Configure WordPress Plugin

Install the F95Zone Crawler plugin on your WordPress site. The plugin provides:
- REST API endpoints for post creation
- Image proxy to handle F95Zone hotlink protection
- Custom post type `f95_game` with category and tag support

### 2. GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- `WORDPRESS_API_URL`: Your WordPress API endpoint (e.g., `http://yoursite.com/wp-json/f95-crawler/v1/create-post`)
- `WORDPRESS_API_KEY`: API key from the WordPress plugin admin page
- `F95_CSRF_TOKEN`: F95Zone `xf_csrf` cookie value
- `F95_SESSION_TOKEN`: F95Zone `xf_session` cookie value  
- `F95_USER_TOKEN`: F95Zone `xf_user` cookie value

### 3. Get F95Zone Cookies

1. Log in to F95Zone in your browser
2. Open Developer Tools (F12) → Application/Storage → Cookies
3. Copy the values for `xf_csrf`, `xf_session`, and `xf_user`

## Usage

### GitHub Actions (Recommended)

The crawler runs automatically every 6 hours via GitHub Actions.

**Manual trigger:**
1. Go to Actions tab in your repository
2. Select "F95Zone Crawler" workflow
3. Click "Run workflow"
4. Optional: Set pages, max threads, and batch size

### Local Usage

```bash
# Install dependencies
pip install requests beautifulsoup4 lxml

# Copy and configure
cp config.json.example config.json
# Edit config.json with your settings

# Run crawler (crawls all pages by default)
python crawler.py

# Crawl specific number of pages
python crawler.py --pages 5

# Limit threads and set batch size
python crawler.py --pages 10 --max-threads 50 --batch-size 10
```

## Configuration

**config.json:**
```json
{
  "wordpress_api_url": "http://yoursite.com/wp-json/f95-crawler/v1/create-post",
  "wordpress_api_key": "your-api-key",
  "delay_between_requests": 2,
  "cookies": [...]
}
```

## Command Line Options

- `--config PATH`: Config file path (default: config.json)
- `--pages N`: Number of category pages to crawl (default: all)
- `--max-threads N`: Maximum threads to process (default: all)
- `--batch-size N`: Batch size for processing (default: 10)

## Data Extracted

- Title, version, developer
- Categories (game type, platforms)
- Tags (content tags from F95Zone)
- Full game description (HTML)
- Screenshots (proxied through WordPress)
- Download links
- Metadata (rating, replies, views, release date, etc.)

## Notes

- Default crawls all pages infinitely
- Duplicate detection prevents re-crawling existing games
- Images are proxied through WordPress to bypass F95Zone hotlink protection
- Respects server with configurable delays between requests
- GitHub Actions logs are saved as artifacts for 7 days

## License

MIT
