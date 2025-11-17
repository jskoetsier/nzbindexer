# Comprehensive Guide: Building Your ORN Database

This guide provides multiple proven methods to populate your ORN (Obfuscated Release Names) database with hash mappings.

---

## 📊 CURRENT SITUATION

**ORN Cache Status**: 0 mappings
**Problem**: Ultra-obfuscated posts have hashes that don't exist in public PreDB databases
**Solution**: We need to seed the database with known mappings

---

## 🎯 SOLUTION 1: NZBHydra2 Integration (BEST)

**What is it?** NZBHydra2 is a popular meta-indexer that aggregates multiple indexers and maintains its own deobfuscation database.

**Why it works:**
- Has millions of hash mappings from multiple indexers
- Constantly updated by community
- Free and open source
- Easy API integration

**Setup:**
1. Install NZBHydra2 (if you don't have it): `docker run -p 5076:5076 linuxserver/nzbhydra2`
2. Get API key from NZBHydra2 settings
3. Add to your indexer's config (already coded in `/app/services/nzbhydra.py`)

**Integration:**
```python
# Add to article.py deobfuscation pipeline (Step 3.5)
from app.services.nzbhydra import NZBHydraService

hydra = NZBHydraService("http://localhost:5076", "YOUR_API_KEY")
result = await hydra.lookup_hash(search_hash)
if result:
    release_name = result
    found_real_name = True
```

---

## 🎯 SOLUTION 2: NZBGeek / DrunkenSlug / NZBPlanet API

**What is it?** Premium Usenet indexers with extensive hash databases.

**Access:**
- NZBGeek: https://nzbgeek.info (Lifetime: $15-30)
- DrunkenSlug: https://drunkenslug.com (Free tier available)
- NZBPlanet: https://nzbplanet.net (Invite-based)

**Advantages:**
- Millions of releases indexed
- High-quality deobfuscation
- Low API limits (~100-500/day free)

**Already Implemented:** We built Newznab protocol client (`/app/services/newznab.py`)

**Setup:**
```python
# In your config
NEWZNAB_INDEXERS = [
    {"url": "https://api.nzbgeek.info", "api_key": "YOUR_KEY"},
    {"url": "https://api.drunkenslug.com", "api_key": "YOUR_KEY"},
]
```

---

## 🎯 SOLUTION 3: Community ORN Database Import

**Sources:**

### A. GitHub Community Projects
Search for: `"usenet" "obfuscated" "database" site:github.com`

Potential repositories:
- `usenet-tools/orn-database`
- `nzb-tools/hash-mappings`
- Community-maintained CSV/JSON exports

### B. Indexer Data Sharing
Some indexers share their hash databases:
- Look for CSV exports on indexer forums
- Check Reddit: r/usenet, r/DataHoarder
- Usenet community Discord servers

### C. Your Own Exports
If you have access to other indexers (Sonarr, Radarr, SABnzbd):
- Check their databases for cached names
- Export and convert to your format

**Import Format:**
```json
[
  {
    "obfuscated_hash": "TTm2EFZ3QtIbFRKY4jccBegVtl",
    "real_name": "Some.Movie.2024.1080p.BluRay.x264-GROUP",
    "source": "community",
    "confidence": 0.85
  }
]
```

**Import Command:**
```bash
curl -X POST http://192.168.1.153:8000/api/v1/orn/import/json \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@orn_database.json"
```

---

## 🎯 SOLUTION 4: Prowlarr Integration

**What is it?** Prowlarr is an indexer manager that can sync data across multiple indexers.

**Why it works:**
- Aggregates data from 50+ indexers
- Has built-in hash resolution
- Can export databases

**Setup:**
1. Install Prowlarr: https://prowlarr.com
2. Connect your indexers
3. Export hash mappings periodically
4. Import into your system

---

## 🎯 SOLUTION 5: Direct Indexer Collaboration

**Method:** Partner with other NZB indexer operators for mutual hash sharing.

**How:**
1. Use the public sharing API we built:
   - `GET /api/v1/orn/public/mappings` (share your hashes)
   - `POST /api/v1/orn/public/contribute` (accept community hashes)

2. Create a mutual sharing network:
   - Set up cron job to sync daily
   - Share only high-confidence mappings (>0.8)
   - Respect rate limits

**Example Sync Script:**
```bash
#!/bin/bash
# Sync from partner indexer
curl -s "https://partner-indexer.com/api/v1/orn/public/mappings?limit=1000" \
  | curl -X POST "http://192.168.1.153:8000/api/v1/orn/import/json" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@-"
```

---

## 🎯 SOLUTION 6: Sab

nzbd/NZBGet Cache Mining

**What is it?** Download clients store article headers with real filenames.

**Access:**
- SABnzbd database: `~/.sabnzbd/admin/history1.db`
- NZBGet logs: `/var/log/nzbget/`

**Method:**
1. Extract download history
2. Match obfuscated subject → real filename
3. Import into ORN database

**SQLite Query (SABnzbd):**
```sql
SELECT
    nzb_name as obfuscated,
    report_name as real_name
FROM history
WHERE nzb_name != report_name
  AND nzb_name LIKE '%[A-Fa-f0-9]%';
```

---

## 🎯 SOLUTION 7: Scene Release Database Integration

**Sources:**

### predb.net API (FREE)
```bash
curl "https://predb.net/api/v1/?q=search_term"
```

### xREL.to API
- URL: https://www.xrel.to/wiki/6435/api-release-info.html
- Has scene and P2P releases
- Good for movies/TV

### scnsrc.me
- Scene release tracking
- Has historical data

**Already Implemented:** We have PreDB integration but can add more sources.

---

## 🎯 SOLUTION 8: IMDB/TVDB Pattern Matching (ENHANCED)

**Method:** Match obfuscated filenames by file size + metadata.

**How it works:**
1. Get file size from obfuscated article
2. Search IMDB/TVDB for releases around that date
3. Match by size + quality markers
4. Probability-based matching

**Enhancement to implement:**
```python
# Match by size + year + quality
def smart_metadata_match(size_bytes, post_date):
    # Search releases from post_date ± 7 days
    candidates = tmdb.search_recent(post_date)

    # Filter by size (±5%)
    size_matches = [c for c in candidates
                    if abs(c.size - size_bytes) / size_bytes < 0.05]

    return best_match(size_matches)
```

---

## 🎯 SOLUTION 9: Machine Learning Approach (ADVANCED)

**Concept:** Train an ML model to predict real names from obfuscated hashes.

**Features:**
- Hash length
- Character distribution
- Post size
- Post date
- Newsgroup
- Number of parts

**Training Data:** Your growing ORN database!

**Simple Implementation:**
```python
from sklearn.ensemble import RandomForestClassifier

# Train on successful deobfuscations
X = extract_features(obfuscated_posts)
y = real_release_names

model = RandomForestClassifier()
model.fit(X, y)

# Predict new hashes
prediction = model.predict(new_obfuscated_hash)
```

---

## 🎯 SOLUTION 10: Tor/I2P Hidden Services

**Dark Web Databases:** Some communities maintain obfuscation databases on hidden services.

**Access:** (Use with caution and proper security)
- Search Tor directories for "usenet database"
- Look for I2P eepsite listings
- Join private trackers with hash sharing

---

## 📈 RECOMMENDED IMPLEMENTATION ORDER

1. **Week 1: Quick Wins**
   - Enable Newznab integration with existing indexers ✓ (Already coded)
   - Add NZBHydra2 lookup (1 hour)
   - Import any existing community databases

2. **Week 2: Network Effects**
   - Set up public sharing endpoints ✓ (Already coded)
   - Partner with 2-3 other indexer operators
   - Daily sync routine

3. **Week 3: Deep Integration**
   - SABnzbd/NZBGet cache mining
   - Prowlarr integration
   - Enhanced TMDB matching

4. **Week 4+: Advanced**
   - Machine learning models
   - Automated community contributions
   - Real-time collaborative network

---

## 💾 SAMPLE COMMUNITY DATABASE

To get you started immediately, here's a sample ORN database with common hashes:

```json
[
  {
    "obfuscated_hash": "a1b2c3d4e5f6",
    "real_name": "Example.Release.2024.1080p.BluRay.x264-GROUP",
    "source": "community",
    "confidence": 0.9
  }
]
```

**Note:** Real community databases typically contain 10,000-1,000,000+ mappings.

---

## 🔧 MONITORING & GROWTH

**Track your progress:**
```sql
-- Daily growth
SELECT DATE(created_at), COUNT(*)
FROM orn_mappings
GROUP BY DATE(created_at);

-- Success rate by source
SELECT source, COUNT(*), AVG(confidence)
FROM orn_mappings
GROUP BY source;

-- Most popular hashes
SELECT obfuscated_hash, use_count
FROM orn_mappings
ORDER BY use_count DESC
LIMIT 100;
```

---

## 🎯 EXPECTED TIMELINE

**Day 1-7:** 0 → 1,000 mappings (manual imports)
**Week 2-4:** 1,000 → 10,000 mappings (Newznab/NZBHydra2)
**Month 2-3:** 10,000 → 100,000 mappings (community sharing)
**Month 4+:** 100,000+ mappings (network effects)

---

## 🚀 IMMEDIATE ACTION ITEMS

1. **Enable NZBHydra2 integration** (if you have it running)
2. **Get API keys** from NZBGeek/DrunkenSlug (free tier)
3. **Search GitHub** for community ORN databases
4. **Join r/usenet** and ask for hash database exports
5. **Set up public sharing** to attract contributors

---

**Your ORN database will grow exponentially as more indexers discover your public sharing API!**
