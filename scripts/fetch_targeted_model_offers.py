from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
TARGETED = ROOT / "input" / "targeted_search"
QUEUE = ROOT / "output" / "firecrawl_offer_queue.csv"
REGISTRY = ROOT / "output" / "source_registry.csv"
ALLOWED_HOST = "allegro.pl"
ACCESSORY_PHRASES = (
    "spiworek", "palak", "barierka", "bumper bar", "bumperbar", "adapter", "torba",
    "folia", "moskitiera", "uchwyt", "wkladka", "organizer", "pokrowiec",
    "czesc zamienna", "czesci zamienne", "zestaw transportowy", "osłona przeciwdeszczowa",
    "oslona przeciwdeszczowa",
)
STROLLER_TERMS = ("wozek", "spacerowka", "stroller", "buggy")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.translate(str.maketrans({"ł": "l", "Ł": "L"}))
    return re.sub(r"\s+", " ", text.lower()).strip()


def product_type_from_title(title: str) -> str:
    """Classify the main listed product, not merely the compatible model."""
    text = normalized_text(title)
    if not text:
        return "unknown"
    has_stroller = any(re.search(rf"\b{re.escape(term)}\b", text) for term in STROLLER_TERMS)
    has_accessory = any(phrase in text for phrase in ACCESSORY_PHRASES)
    # A title that explicitly sells a stroller remains a stroller even when it
    # mentions an included accessory. Accessory-only titles say "do wózka" or
    # "do ORFEO" but do not name the stroller as the main item.
    if has_stroller:
        return "stroller"
    if has_accessory:
        return "accessory"
    return "unknown"


def decode_url(value: str) -> str:
    result = html.unescape(value or "")
    for _ in range(3):
        decoded = unquote(result)
        if decoded == result:
            break
        result = decoded
    encoded = re.search(r"[?&]redirect=([A-Za-z0-9_-]{20,})(?:&|$)", result)
    if encoded and "/dss-proxy/clicks" in result:
        try:
            raw = encoded.group(1); raw += "=" * (-len(raw) % 4)
            decoded_redirect = base64.urlsafe_b64decode(raw).decode("utf-8")
            result = result + "&redirect_decoded=" + unquote(decoded_redirect)
        except (ValueError, UnicodeDecodeError):
            pass
    return result


def redirect_target(url: str) -> str:
    """Unwrap redirect links and return the direct Allegro target."""
    decoded = decode_url(url)
    marker = re.search(r"[?&]redirect_decoded=(https?://.+)$", decoded, re.I)
    if marker:
        decoded = marker.group(1)
    marker = re.search(
        r"[?&]redirect=(https?://.*?(?:/oferta/|/produkt/)[^&#?]*?-\d{6,})",
        decoded,
        re.I,
    )
    if marker:
        decoded = marker.group(1)
    return html.unescape(unquote(decoded))


def offer_id_from_url(url: str) -> str:
    decoded = redirect_target(url)
    embedded = re.search(r"/(?:oferta|produkt)/[^?#]*?[-_/](\d{6,})(?:[/?#&]|$)", decoded, re.I)
    if embedded:
        return embedded.group(1)
    parsed = urlparse(decoded)
    query = parse_qs(parsed.query)
    for key in ("offerId", "offer_id", "emission_element_id"):
        for value in query.get(key, []):
            match = re.search(r"\d{6,}", value)
            if match:
                return match.group(0)
    match = re.search(r"(?:/oferta/|/produkt/)[^?#]*?[-_/](\d{6,})(?:[/?#]|$)", parsed.path, re.I)
    return match.group(1) if match else ""


def canonical_url(url: str) -> str:
    decoded = redirect_target(url)
    offer_id = offer_id_from_url(decoded)
    parsed = urlparse(decoded)
    if offer_id and parsed.netloc.lower().endswith(ALLOWED_HOST):
        match = re.search(r"/(?:oferta|produkt)/([^/?#]+)", parsed.path, re.I)
        if match:
            product_slug = re.sub(
                r"-[0-9a-f]{8}-[0-9a-f-]{27,}$", "", match.group(1), flags=re.I
            )
            product_slug = re.sub(rf"-{re.escape(offer_id)}$", "", product_slug)
            return f"https://allegro.pl/oferta/{product_slug}-{offer_id}"
    return decoded


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.current=None; self.text=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag.lower()=='a' and attrs.get('href'):
            self.current=attrs['href']; self.text=[]
    def handle_data(self, data):
        if self.current is not None:self.text.append(data)
    def handle_endtag(self, tag):
        if tag.lower()=='a' and self.current is not None:
            # Preserve exactly what was present in the source HTML.
            self.links.append((html.unescape(self.current), ' '.join(' '.join(self.text).split())))
            self.current=None; self.text=[]


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class ArticleParser(HTMLParser):
    """Collect each main listing card without relying on Allegro CSS classes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.text: list[str] = []
        self.urls: list[str] = []
        self.articles: list[dict[str, object]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "article" and self.depth == 0:
            self.depth = 1
            self.text = []
            self.urls = []
            return
        if self.depth == 0:
            return
        if tag == "a" and attributes.get("href"):
            self.urls.append(html.unescape(attributes["href"]))
        if tag not in VOID_TAGS:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if self.depth and tag == "a":
            attributes = dict(attrs)
            if attributes.get("href"):
                self.urls.append(html.unescape(attributes["href"]))

    def handle_data(self, data):
        if self.depth:
            self.text.append(data)

    def handle_endtag(self, tag):
        if self.depth == 0 or tag in VOID_TAGS:
            return
        self.depth -= 1
        if self.depth == 0:
            self.articles.append({
                "text": " ".join(" ".join(self.text).split()),
                "urls": self.urls,
            })


def extract_price(text: str) -> tuple[str, str]:
    match = re.search(r"\b(\d{1,3}(?:[ .]\d{3})*|\d+)\s*,\s*(\d{2})\s*(zł|pln)\b", text, re.I)
    if not match:
        return "", ""
    whole = match.group(1).replace(" ", "").replace(".", "")
    return f"{whole},{match.group(2)} zł", "PLN"


def extract_condition(text: str) -> str:
    match = re.search(
        r"\bStan\s+([A-Za-zÀ-žąćęłńóśźżĄĆĘŁŃÓŚŹŻ -]{2,80}?)(?=\s+\d[\d .,]*\s*(?:zł|PLN)\b|\s+dostawa\b|$)",
        text,
        re.I,
    )
    return " ".join(match.group(1).split()) if match else ""


def listing_offer_details(markup: str) -> dict[str, dict]:
    """Map card-local facts to offer IDs, leaving unavailable seller data empty."""
    parser = ArticleParser()
    parser.feed(html.unescape(markup or ""))
    details: dict[str, dict] = {}
    for article in parser.articles:
        text = str(article["text"])
        offer_ids = {offer_id_from_url(url) for url in article["urls"] if offer_id_from_url(url)}
        if not offer_ids:
            continue
        price, currency = extract_price(text)
        card = {
            "price": price,
            "currency": currency,
            "condition": extract_condition(text),
            "sponsored": bool(re.search(r"\bSponsorowane\b", text, re.I)),
            # This listing snapshot does not expose seller identity or seller
            # reputation inside an offer card. Do not infer either field.
            "seller_name": None,
            "seller_type": None,
            "seller_rating": None,
            "seller_reviews_count": None,
            "duplicate_count": 0,
        }
        for offer_id in offer_ids:
            existing = details.get(offer_id)
            if existing is None:
                details[offer_id] = card
            else:
                existing["duplicate_count"] = int(existing.get("duplicate_count", 0)) + 1
                if not existing.get("price") and price:
                    existing.update(card)
    return details


def extract_offers(markup: str, brand: str, model: str) -> tuple[list[dict], list[dict]]:
    parser=LinkParser(); parser.feed(html.unescape(markup or ""))
    card_details = listing_offer_details(markup)
    model_tokens=re.findall(r"[\wÀ-ž]+", normalized_text(model))
    text_model_tokens=[token for token in model_tokens if not token.isdigit()]
    numeric_model_tokens=[token for token in model_tokens if token.isdigit()]
    accepted={}; rejected=[]; seen_links=set()
    for original,title in parser.links:
        if original in seen_links and not title: continue
        seen_links.add(original); oid=offer_id_from_url(original); lower=normalized_text(title); tokens=re.findall(r"[\wÀ-ž]+", lower)
        normalized_brand = normalized_text(brand)
        brand_match=normalized_brand in tokens
        text_model_match=bool(text_model_tokens) and all(token in tokens for token in text_model_tokens)
        numeric_model_match=all(token in tokens for token in numeric_model_tokens)
        model_match=bool(model_tokens) and text_model_match and numeric_model_match
        previous_generation=bool(text_model_match and numeric_model_tokens and not numeric_model_match)
        product_type = product_type_from_title(title)
        decoded_url = redirect_target(original)
        is_offer=bool(oid) and ("/oferta/" in decoded_url or "/produkt/" in decoded_url or "/events/clicks" in original or "/dss-proxy/clicks" in original)
        reason=""
        if not is_offer:
            reason="not_an_offer_link"
            match_status="rejected"
        elif product_type == "accessory":
            reason="accessory"
            match_status="rejected"
        elif brand_match and model_match and product_type == "stroller":
            match_status="exact_match"
        elif brand_match and model_match:
            reason="product_type_unknown"
            match_status="uncertain"
        elif brand_match and previous_generation and product_type == "stroller":
            # A model name without a required numeric variant is a plausible
            # older generation, never an exact match for the requested model.
            reason="previous_generation"
            match_status="uncertain"
        elif not brand_match:
            reason="brand_mismatch"
            match_status="rejected"
        else:
            reason="model_mismatch"
            match_status="rejected"
        is_accepted = match_status == "exact_match"
        record={"offer_id":oid,"title":title,"canonical_url":canonical_url(original),"original_url":original,"brand_match":brand_match,"model_match":model_match,"previous_generation":previous_generation,"product_type":product_type,"match_status":match_status,"accepted":is_accepted,"rejection_reason":reason, **card_details.get(oid, {})}
        if is_accepted:
            accepted.setdefault(oid,record)
        elif oid and oid not in accepted:
            rejected.append(record)
    rejected_by_id = {}
    for item in rejected:
        if item["offer_id"] in accepted:
            continue
        if item["offer_id"] not in rejected_by_id or (not rejected_by_id[item["offer_id"]]["title"] and item["title"]):
            rejected_by_id[item["offer_id"]] = item
    return list(accepted.values()), list(rejected_by_id.values())


def known_offer_ids() -> set[str]:
    known=set()
    for path in (QUEUE, REGISTRY):
        if path.exists():
            with path.open(encoding='utf-8',newline='') as handle:
                for row in csv.DictReader(handle):
                    known.add(str(row.get('offer_id') or row.get('external_offer_id') or ''))
    return {value for value in known if value}


def fetch_live(url: str) -> dict:
    from fetch_firecrawl_offer_pages import require_api_key, scrape_offer
    return scrape_offer(url, require_api_key())


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--marketplace',required=True); parser.add_argument('--brand',required=True); parser.add_argument('--model',required=True); parser.add_argument('--apply',action='store_true'); parser.add_argument('--input-html'); args=parser.parse_args()
    if args.marketplace.lower()!='allegro': print(f"Marketplace '{args.marketplace}' nie ma jeszcze adaptera targeted research."); return 1
    directory=TARGETED/f'{slug(args.brand)}__{slug(args.model)}'/'allegro'; directory.mkdir(parents=True,exist_ok=True)
    search_url=f'https://allegro.pl/listing?string={args.brand}+{args.model}'
    if args.input_html:
        markup=Path(args.input_html).read_text(encoding='utf-8',errors='replace') if Path(args.input_html).exists() else ''
        response={'success':True,'data':{'html':markup,'markdown':'','metadata':{'sourceURL':search_url}}}
    else:
        if not os.getenv('FIRECRAWL_API_KEY','').strip(): print('Brak FIRECRAWL_API_KEY. Użyj --input-html albo ustaw zmienną środowiskową.'); return 1
        response=fetch_live(search_url); data=response.get('data',response); markup=str(data.get('html',''))
    (directory/'listing.html').write_text(markup,encoding='utf-8'); (directory/'listing.md').write_text(str(response.get('data',response).get('markdown','')),encoding='utf-8'); (directory/'raw_response.json').write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8'); (directory/'metadata.json').write_text(json.dumps(response.get('data',response).get('metadata',{}),ensure_ascii=False,indent=2),encoding='utf-8')
    accepted,rejected=extract_offers(markup,args.brand,args.model); known=known_offer_ids(); extracted=[]; new=[]
    for item in accepted:
        item['accepted'] = item.get('match_status') == 'exact_match'
        item['already_known']=item['offer_id'] in known
        if not item['already_known']: new.append(item)
        extracted.append(item)
    (directory/'extracted_offers.json').write_text(json.dumps(extracted,ensure_ascii=False,indent=2),encoding='utf-8'); (directory/'rejected_offers.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2),encoding='utf-8')
    columns=('external_offer_id','source_url','canonical_url','title','brand_match','model_match','accepted','rejection_reason')
    with (directory/'new_offers.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=columns); writer.writeheader(); writer.writerows({'external_offer_id':item['offer_id'],'source_url':item['original_url'],'canonical_url':item['canonical_url'],'title':item['title'],'brand_match':item['brand_match'],'model_match':item['model_match'],'accepted':True,'rejection_reason':''} for item in new)
    unique_records = accepted + rejected
    unique_offer_ids = len({x['offer_id'] for x in unique_records if x['offer_id']})
    all_records = accepted + rejected
    summary={'marketplace':args.marketplace.lower(),'brand':args.brand,'model':args.model,'cards_found':unique_offer_ids,'unique_offer_ids':unique_offer_ids,'accepted_model_offers':len(accepted),'rejected_other_models':len(rejected),'strollers_found':sum(1 for item in all_records if item.get('product_type') == 'stroller'),'accessories_rejected':sum(1 for item in all_records if item.get('product_type') == 'accessory'),'unknown_offers':sum(1 for item in all_records if item.get('product_type') == 'unknown'),'already_known':sum(1 for x in extracted if x['already_known']),'new_offers':len(new),'applied':False,'created_at':datetime.now(timezone.utc).isoformat()}
    if args.apply and new:
        result=subprocess.run([sys.executable,str(ROOT/'scripts/merge_targeted_model_offers.py'),'--marketplace','allegro','--brand',args.brand,'--model',args.model,'--input-csv',str(directory/'new_offers.csv')],cwd=ROOT,capture_output=True,text=True); summary['applied']=result.returncode==0
    (directory/'research_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for key,value in summary.items():
        if key not in {'created_at'}: print(f'{key}={value}')
    return 0
if __name__=='__main__':raise SystemExit(main())
