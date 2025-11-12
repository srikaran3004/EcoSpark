from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import F
from .models import RecyclingCenter, Device, UserCredit, Pickup, Challenge, ChallengeCompletion
from .utils.ai import get_ai_explanation
from django.http import JsonResponse
from .forms import UserRegistrationForm, UserLoginForm, UserProfileUpdateForm, CustomPasswordChangeForm
import requests
import os


def home(request):
    return render(request, 'home.html')


def centers(request):
    centers_qs = RecyclingCenter.objects.all()
    centers_data = [
        {
            "name": c.name,
            "address": c.address,
            "latitude": c.latitude,
            "longitude": c.longitude,
        }
        for c in centers_qs
    ]
    return render(request, 'centers.html', {"centers": centers_data})


def education(request):
    ai_text = None
    topic = None
    if request.method == 'POST':
        topic = request.POST.get('topic', '').strip()
        if topic:
            # More specific prompt for e-waste components
            prompt = (
                f"Explain why '{topic}' in electronic waste (e-waste) is harmful to human health and the environment. "
                f"Focus specifically on '{topic}' as an e-waste component. If '{topic}' is not typically found in e-waste, "
                f"clarify that and suggest relevant e-waste components instead. Keep the explanation to 3-4 clear sentences."
            )
            ai_text = get_ai_explanation(prompt)
        else:
            messages.warning(request, "Please enter a component to learn about.")
    return render(request, 'education.html', {"ai_text": ai_text, "topic": topic})


def _get_or_create_user_credit(user):
    if not user.is_authenticated:
        return None
    credit, _ = UserCredit.objects.get_or_create(user=user, defaults={"points": 0})
    return credit


def credits(request):
    result = None
    balance = None
    if request.method == 'POST':
        model_name = request.POST.get('device_model', '').strip()
        if not model_name:
            messages.warning(request, "Please enter a device model.")
        else:
            device = Device.objects.filter(model_name__iexact=model_name).first()
            if not device:
                messages.error(request, "Device model not found. Please ask admin to add it.")
            else:
                points_awarded = int(round(device.metal_value * 10))

                credit = _get_or_create_user_credit(request.user)
                if credit:
                    credit.points = F('points') + points_awarded
                    credit.save()
                    credit.refresh_from_db()
                    balance = credit.points
                    result = {
                        "model_name": device.model_name,
                        "metal_value": device.metal_value,
                        "points_awarded": points_awarded,
                        "saved": True,
                    }
                    messages.success(request, f"{points_awarded} points added to your balance.")
                else:
                    # Anonymous user: show computed points but don't persist
                    result = {
                        "model_name": device.model_name,
                        "metal_value": device.metal_value,
                        "points_awarded": points_awarded,
                        "saved": False,
                    }
                    messages.info(request, "Login to save your points.")

    if request.user.is_authenticated:
        credit = _get_or_create_user_credit(request.user)
        balance = credit.points if credit else 0

    return render(request, 'credits.html', {"result": result, "balance": balance})


def centers_nearby_api(request):
    """
    Return nearby recycling centers using Google Places (New API v1) when configured,
    or Yelp as fallback. Results are constrained by provided location/radius and can
    be additionally filtered to the current map bounds to avoid cross-country noise.

    GET params:
      - q: optional text query for place/area (e.g., city name)
      - country: optional 2-letter country code (in, us, gb, ca, au)
      - lat, lng: center to search around (preferred)
      - radius_km: search radius in kilometers (1..50, default 10)
      - sw_lat, sw_lng, ne_lat, ne_lng: optional map bounds to hard-filter results
    """
    q = (request.GET.get('q') or '').strip()
    country_code = (request.GET.get('country') or '').strip().lower()
    lat_param = request.GET.get('lat')
    lng_param = request.GET.get('lng')
    lat = None
    lng = None
    if lat_param and lng_param:
        try:
            lat = float(lat_param)
            lng = float(lng_param)
        except (TypeError, ValueError):
            lat = None
            lng = None

    try:
        radius_km = float(request.GET.get('radius_km', 10))
    except ValueError:
        radius_km = 10.0

    radius_m = int(min(max(radius_km, 1), 50) * 1000)  # clamp 1km..50km

    # Optional bounds (to constrain results to visible map)
    def _parse_float(val):
        try:
            return float(val)
        except Exception:
            return None

    sw_lat = _parse_float(request.GET.get('sw_lat'))
    sw_lng = _parse_float(request.GET.get('sw_lng'))
    ne_lat = _parse_float(request.GET.get('ne_lat'))
    ne_lng = _parse_float(request.GET.get('ne_lng'))

    def _within_bounds(lat_v, lng_v):
        if None in (sw_lat, sw_lng, ne_lat, ne_lng):
            return True  # no bounds provided
        try:
            # Simple bbox (non-antimeridian)
            return (sw_lat <= lat_v <= ne_lat) and (sw_lng <= lng_v <= ne_lng)
        except Exception:
            return True

    # Prefer Google Places if API key present; otherwise use Yelp Fusion
    gmaps_key = os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('GOOGLE_PLACES_API_KEY')
    yelp_key = os.getenv('YELP_API_KEY')

    results = []

    if gmaps_key:
        try:
            # Google Places API (New) v1
            headers = {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': gmaps_key,
                'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.userRatingCount,places.nationalPhoneNumber,places.websiteUri',
            }

            # If a textual place query is provided, resolve it first to lat/lng using Text Search with country bias
            if q and (lat is None or lng is None):
                country_name_map = {
                    'in': 'India', 'us': 'USA', 'gb': 'UK', 'ca': 'Canada', 'au': 'Australia'
                }
                country_label = country_name_map.get(country_code, country_code.upper() if country_code else '')
                text_query = f"{q}{', ' + country_label if country_label else ''}"
                text_url = 'https://places.googleapis.com/v1/places:searchText'
                text_payload = {
                    "textQuery": text_query,
                    # Help Google bias the result to our selected country or current map bounds
                    "maxResultCount": 1
                }
                # Prefer regionCode if provided
                if country_code:
                    text_payload["regionCode"] = country_code.upper()
                # If bounds provided from map, bias to rectangle
                if None not in (sw_lat, sw_lng, ne_lat, ne_lng):
                    text_payload["locationBias"] = {
                        "rectangle": {
                            "low": {"latitude": sw_lat, "longitude": sw_lng},
                            "high": {"latitude": ne_lat, "longitude": ne_lng}
                        }
                    }
                tr0 = requests.post(text_url, json=text_payload, headers=headers, timeout=20)
                if tr0.status_code == 200:
                    t0 = tr0.json()
                    if t0.get('places'):
                        loc0 = (t0['places'][0].get('location') or {})
                        if 'latitude' in loc0 and 'longitude' in loc0:
                            lat = float(loc0['latitude'])
                            lng = float(loc0['longitude'])
                # If still missing, return informative message
                if lat is None or lng is None:
                    return JsonResponse({'centers': [], 'provider': 'google_places_new_text_geocode', 'error': 'Could not resolve place to coordinates', 'query': text_query}, status=400)

            # Nearby search (New API)
            nearby_url = 'https://places.googleapis.com/v1/places:searchNearby'
            nearby_payload = {
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lng},
                        "radius": float(radius_m)
                    }
                },
                # Use focused types to avoid irrelevant results
                "includedTypes": ["recycling_center", "electronics_store"],
                "rankPreference": "DISTANCE",
                "maxResultCount": 20
            }
            nr = requests.post(nearby_url, json=nearby_payload, headers=headers, timeout=20)
            if nr.status_code != 200:
                # Capture error details and fall back to Text Search
                try:
                    err_json = nr.json()
                except Exception:
                    err_json = {"raw": nr.text}
                # Try Text Search directly on error
                text_url = 'https://places.googleapis.com/v1/places:searchText'
                text_payload = {
                    "textQuery": f"electronics recycling near {lat},{lng}",
                    "locationBias": {
                        "circle": {
                            "center": {"latitude": lat, "longitude": lng},
                            "radius": float(radius_m)
                        }
                    },
                    "maxResultCount": 20
                }
                if country_code:
                    text_payload["regionCode"] = country_code.upper()
                tr = requests.post(text_url, json=text_payload, headers=headers, timeout=20)
                if tr.status_code != 200:
                    try:
                        t_err = tr.json()
                    except Exception:
                        t_err = {"raw": tr.text}
                    return JsonResponse({
                        'centers': [],
                        'provider': 'google_places_new',
                        'nearby_error': err_json,
                        'textsearch_error': t_err,
                    }, status=502)
                ndata = {"places": []}
                tdata = tr.json()
                for p in tdata.get('places', []):
                    loc = p.get('location') or {}
                    name = (p.get('displayName') or {}).get('text') or 'Recycling Center'
                    address = p.get('formattedAddress') or 'Address unavailable'
                    if 'latitude' in loc and 'longitude' in loc:
                        lat_v = float(loc['latitude'])
                        lng_v = float(loc['longitude'])
                        if not _within_bounds(lat_v, lng_v):
                            continue
                        results.append({
                            'name': name,
                            'address': address,
                            'latitude': lat_v,
                            'longitude': lng_v,
                            'source': 'google_places_new_text',
                        })
                return JsonResponse({'centers': results})
            else:
                ndata = nr.json()

            exclude_us = (country_code and country_code != 'us')  # if user explicitly selected another country
            for p in ndata.get('places', []):
                loc = p.get('location') or {}
                name = (p.get('displayName') or {}).get('text') or 'Recycling Center'
                address = p.get('formattedAddress') or 'Address unavailable'
                # Basic blacklist for USA
                if exclude_us and address and ('United States' in address or address.endswith(', USA')):
                    continue
                if 'latitude' in loc and 'longitude' in loc:
                    # Additional coarse filter by longitude (USA longitudes are typically negative large)
                    try:
                        if exclude_us and float(loc['longitude']) < -30:
                            continue
                    except Exception:
                        pass
                    lat_v = float(loc['latitude'])
                    lng_v = float(loc['longitude'])
                    if not _within_bounds(lat_v, lng_v):
                        continue
                    results.append({
                        'name': name,
                        'address': address,
                        'latitude': lat_v,
                        'longitude': lng_v,
                        'source': 'google_places_new_nearby',
                        'types': p.get('types') or [],
                        'rating': p.get('rating'),
                        'userRatingCount': p.get('userRatingCount'),
                        'phone': p.get('nationalPhoneNumber'),
                        'website': p.get('websiteUri'),
                    })

            # If none found, try text search (broader)
            if not results:
                text_url = 'https://places.googleapis.com/v1/places:searchText'
                text_payload = {
                    "textQuery": f"electronics recycling near {lat},{lng}",
                    "locationBias": {
                        "circle": {
                            "center": {"latitude": lat, "longitude": lng},
                            "radius": float(radius_m)
                        }
                    },
                    "maxResultCount": 20
                }
                if country_code:
                    text_payload["regionCode"] = country_code.upper()
                tr = requests.post(text_url, json=text_payload, headers=headers, timeout=20)
                if tr.status_code != 200:
                    try:
                        terr = tr.json()
                    except Exception:
                        terr = {"raw": tr.text}
                    return JsonResponse({'centers': [], 'provider': 'google_places_new_text', 'error': terr}, status=502)
                tdata = tr.json()
                for p in tdata.get('places', []):
                    loc = p.get('location') or {}
                    name = (p.get('displayName') or {}).get('text') or 'Recycling Center'
                    address = p.get('formattedAddress') or 'Address unavailable'
                    if exclude_us and address and ('United States' in address or address.endswith(', USA')):
                        continue
                    if 'latitude' in loc and 'longitude' in loc:
                        try:
                            if exclude_us and float(loc['longitude']) < -30:
                                continue
                        except Exception:
                            pass
                        lat_v = float(loc['latitude'])
                        lng_v = float(loc['longitude'])
                        if not _within_bounds(lat_v, lng_v):
                            continue
                        results.append({
                            'name': name,
                            'address': address,
                            'latitude': lat_v,
                            'longitude': lng_v,
                            'source': 'google_places_new_text',
                            'types': p.get('types') or [],
                            'rating': p.get('rating'),
                            'userRatingCount': p.get('userRatingCount'),
                            'phone': p.get('nationalPhoneNumber'),
                            'website': p.get('websiteUri'),
                        })

            return JsonResponse({'centers': results})
        except Exception as e:
            return JsonResponse({'error': f'Google Places (New) failed: {e}'}, status=502)

    if yelp_key:
        try:
            headers = {'Authorization': f'Bearer {yelp_key}'}
            url = 'https://api.yelp.com/v3/businesses/search'
            params = {
                'term': 'electronics recycling, e-waste recycling, recycling center',
                'latitude': lat,
                'longitude': lng,
                'radius': radius_m,
                'limit': 30,
            }
            r = requests.get(url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            for b in data.get('businesses', []):
                coords = b.get('coordinates', {})
                name = b.get('name') or 'Recycling Center'
                addr = ", ".join(b.get('location', {}).get('display_address') or []) or 'Address unavailable'
                if coords.get('latitude') and coords.get('longitude'):
                    results.append({
                        'name': name,
                        'address': addr,
                        'latitude': coords['latitude'],
                        'longitude': coords['longitude'],
                        'source': 'yelp',
                    })
            return JsonResponse({'centers': results})
        except Exception as e:
            return JsonResponse({'error': f'Yelp search failed: {e}'}, status=502)

    return JsonResponse({
        'error': 'No external provider configured. Set GOOGLE_MAPS_API_KEY (or GOOGLE_PLACES_API_KEY) or YELP_API_KEY in .env.'
    }, status=412)


# ---------- New AI-powered features (no database) ----------

import datetime


def eco_tips(request):
    """
    Generate a short daily eco-friendly tip using AI. Uses date to vary tip; no DB.
    """
    today = datetime.date.today().isoformat()
    tip = get_ai_explanation(
        f"Provide one practical eco-friendly tip for daily life, related to e-waste, energy saving, or recycling. "
        f"Keep it to 1–2 sentences, friendly in tone. Date context: {today}."
    )
    return render(request, 'eco_tips.html', {"tip": tip, "date": today})


def quiz(request):
    """
    AI-generated 5-question multiple-choice quiz. No persistence.
    """
    import json
    questions = []
    if request.method == 'GET' or request.GET.get('regen') == '1':
        instruction = (
            "Create 5 multiple-choice questions about e-waste, sustainability, or recycling. "
            "For each question, include exactly 4 options labeled A, B, C, D and provide the correct answer letter. "
            "Return clearly; keep questions concise."
        )
        raw = get_ai_explanation(instruction)
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        current = {"q": "", "options": [], "answer": None}
        for ln in lines:
            if len(questions) >= 5:
                break
            lnu = ln.upper()
            if lnu.startswith(('1.', '2.', '3.', '4.', '5.', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5')):
                if current["q"]:
                    questions.append(current)
                current = {"q": ln.split('.', 1)[-1].strip() or ln, "options": [], "answer": None}
            elif lnu.startswith(('A:', 'B:', 'C:', 'D:')) or (len(lnu) > 2 and lnu[1] == ')' and lnu[0] in 'ABCD'):
                label = lnu[0]
                text = ln[2:].strip() if ':' in ln[:3] else ln[3:].strip()
                current["options"].append({"label": label, "text": text})
            elif lnu.startswith(('ANSWER:', 'CORRECT:', 'ANS:')):
                for ch in ('A','B','C','D'):
                    if ch in lnu:
                        current["answer"] = ch
                        break
        if current["q"] and len(questions) < 5:
            questions.append(current)
        questions = [q for q in questions if q.get('q') and len(q.get('options', [])) == 4 and q.get('answer') in ('A','B','C','D')]
        while len(questions) < 5:
            idx = len(questions) + 1
            questions.append({
                "q": f"Which is best for e-waste? (Q{idx})",
                "options": [
                    {"label": "A", "text": "Throw in regular trash"},
                    {"label": "B", "text": "Burn to reduce volume"},
                    {"label": "C", "text": "Recycle at certified center"},
                    {"label": "D", "text": "Dump in river"},
                ],
                "answer": "C",
            })

    user_answers = {}
    score = None
    if request.method == 'POST':
        try:
            questions = json.loads(request.POST.get('questions_json') or '[]')
        except Exception:
            questions = []
        for i in range(5):
            user_answers[str(i)] = request.POST.get(f'q{i}')
        correct = 0
        for i, q in enumerate(questions[:5]):
            if user_answers.get(str(i)) == q.get('answer'):
                correct += 1
        score = correct
        # attach user choice to each question for template rendering without custom filters
        for i, q in enumerate(questions[:5]):
            q['user_choice'] = user_answers.get(str(i))

    return render(request, 'quiz.html', {"questions": questions[:5], "user_answers": user_answers, "score": score})


def decision(request):
    """
    Recycle-or-Reuse helper: returns decision and reasoning via AI.
    """
    result = None
    item = None
    if request.method == 'POST':
        item = (request.POST.get('item') or '').strip()
        if item:
            # More structured prompt to get accurate decision
            prompt = (
                f"Analyze the item '{item}' and determine if it should be RECYCLED or REUSED. "
                f"Consider: Can it be repaired and used again? Is it too old or broken? "
                f"Respond in this exact format: First line: 'RECOMMENDATION: [Recycle OR Reuse]' "
                f"Second line: A brief 2-3 sentence explanation of why this is the best option, "
                f"focusing specifically on '{item}' and its condition/age."
            )
            text = get_ai_explanation(prompt)
            
            # Parse the response to extract decision and reason
            decision_word = 'Recycle'
            reason = text
            
            # Try to extract recommendation from response
            if 'RECOMMENDATION:' in text.upper():
                parts = text.split('RECOMMENDATION:', 1)
                if len(parts) > 1:
                    rec_line = parts[1].split('\n')[0].strip()
                    if 'reuse' in rec_line.lower():
                        decision_word = 'Reuse'
                    reason = parts[1].strip() if len(parts) > 1 else text
            elif text.lower().startswith('reuse') or ' reuse ' in text.lower()[:50]:
                decision_word = 'Reuse'
            
            result = {"decision": decision_word, "reason": reason}
    return render(request, 'decision.html', {"item": item, "result": result})


# ---------- Reuse Marketplace (no DB) ----------
def reuse_marketplace(request):
    """
    Suggest sell/donate/recycle using AI reasoning. Fetches nearby repair shops if location provided.
    """
    recommendation = None
    reasoning = None
    suggestions = []
    needs_location = False
    user_lat = None
    user_lng = None

    if request.method == 'POST':
        model = (request.POST.get('model') or '').strip()
        condition = (request.POST.get('condition') or '').strip().lower()
        age = (request.POST.get('age') or '').strip()
        
        # Get user location if provided
        user_lat = request.POST.get('lat')
        user_lng = request.POST.get('lng')
        
        # Better AI prompt for recommendation
        prompt = (
            f"For a {model or 'electronic device'} that is {age or 'unknown'} years old with condition: {condition or 'unspecified'}, "
            f"recommend the best action: SELL, DONATE, REPAIR, or RECYCLE. "
            f"Format your response as: 'RECOMMENDATION: [Action]' on first line, "
            f"then 2-3 sentences explaining why this is best, considering age, condition, and environmental impact."
        )
        ai_response = get_ai_explanation(prompt)
        
        # Parse recommendation
        if 'RECOMMENDATION:' in ai_response.upper():
            parts = ai_response.split('RECOMMENDATION:', 1)
            if len(parts) > 1:
                recommendation = parts[1].split('\n')[0].strip()
                reasoning = parts[1].strip() if len(parts) > 1 else ai_response
        else:
            # Fallback parsing
            if 'sell' in ai_response.lower()[:100]:
                recommendation = 'Sell'
            elif 'donate' in ai_response.lower()[:100]:
                recommendation = 'Donate'
            elif 'repair' in ai_response.lower()[:100]:
                recommendation = 'Repair'
            else:
                recommendation = 'Recycle'
            reasoning = ai_response
        
        # Check if repair/reuse is recommended and location is needed
        if recommendation and ('repair' in recommendation.lower() or 'reuse' in recommendation.lower() or 'donate' in recommendation.lower()):
            needs_location = True
            
            # Fetch nearby repair shops if location provided
            if user_lat and user_lng:
                try:
                    api_key = os.getenv('GOOGLE_MAPS_API_KEY')
                    if api_key:
                        # Determine device type from model to search for appropriate repair shops
                        model_lower = model.lower() if model else ''
                        search_query = None
                        place_types = []
                        
                        # Detect device type and set appropriate search terms
                        if any(term in model_lower for term in ['phone', 'iphone', 'samsung', 'mobile', 'smartphone', 'android']):
                            search_query = "mobile phone repair shop"
                            place_types = ["electronics_store"]
                        elif any(term in model_lower for term in ['laptop', 'notebook', 'macbook', 'dell', 'hp', 'lenovo', 'asus']):
                            search_query = "laptop computer repair shop"
                            place_types = ["electronics_store"]
                        elif any(term in model_lower for term in ['tv', 'television', 'monitor', 'display']):
                            search_query = "TV electronics repair shop"
                            place_types = ["electronics_store"]
                        else:
                            # Generic electronics repair
                            search_query = "electronics repair shop"
                            place_types = ["electronics_store"]
                        
                        # Try text search first (more accurate for specific repair shops)
                        text_search_url = "https://places.googleapis.com/v1/places:searchText"
                        text_headers = {
                            'Content-Type': 'application/json',
                            'X-Goog-Api-Key': api_key,
                            'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.rating,places.types'
                        }
                        text_payload = {
                            "textQuery": f"{search_query} near {float(user_lat)},{float(user_lng)}",
                            "maxResultCount": 5,
                            "locationBias": {
                                "circle": {
                                    "center": {
                                        "latitude": float(user_lat),
                                        "longitude": float(user_lng)
                                    },
                                    "radius": 10000  # 10km
                                }
                            }
                        }
                        
                        try:
                            response = requests.post(text_search_url, json=text_payload, headers=text_headers, timeout=5)
                            if response.status_code == 200:
                                data = response.json()
                                if 'places' in data:
                                    # Filter results to ensure they're repair-related
                                    for place in data['places']:
                                        place_name = place.get('displayName', {}).get('text', '').lower()
                                        place_types_list = place.get('types', [])
                                        
                                        # Only include if it's clearly a repair shop
                                        if any(keyword in place_name for keyword in ['repair', 'service', 'fix', 'mobile', 'phone', 'laptop', 'computer', 'electronics']) or \
                                           any(pt in place_types_list for pt in ['electronics_store', 'store']):
                                            suggestions.append({
                                                "name": place.get('displayName', {}).get('text', 'Unknown'),
                                                "address": place.get('formattedAddress', 'Address not available'),
                                                "phone": place.get('nationalPhoneNumber', 'Phone not available'),
                                                "rating": place.get('rating', 'N/A')
                                            })
                                            if len(suggestions) >= 5:
                                                break
                        except Exception as e:
                            pass  # Fallback to nearby search
                        
                        # Fallback to nearby search if text search didn't return enough results
                        if len(suggestions) < 3:
                            nearby_url = "https://places.googleapis.com/v1/places:searchNearby"
                            nearby_headers = {
                                'Content-Type': 'application/json',
                                'X-Goog-Api-Key': api_key,
                                'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.rating,places.types'
                            }
                            nearby_payload = {
                                "includedTypes": place_types if place_types else ["electronics_store"],
                                "maxResultCount": 5,
                                "locationRestriction": {
                                    "circle": {
                                        "center": {
                                            "latitude": float(user_lat),
                                            "longitude": float(user_lng)
                                        },
                                        "radius": 10000  # 10km
                                    }
                                }
                            }
                            try:
                                response = requests.post(nearby_url, json=nearby_payload, headers=nearby_headers, timeout=5)
                                if response.status_code == 200:
                                    data = response.json()
                                    if 'places' in data:
                                        for place in data['places']:
                                            place_name = place.get('displayName', {}).get('text', '').lower()
                                            # Filter out supermarkets and irrelevant stores
                                            if not any(exclude in place_name for exclude in ['supermarket', 'grocery', 'mall', 'department store', 'retail']):
                                                if any(keyword in place_name for keyword in ['repair', 'service', 'fix', 'mobile', 'phone', 'laptop', 'computer', 'electronics']) or \
                                                   place.get('types', []):
                                                    suggestions.append({
                                                        "name": place.get('displayName', {}).get('text', 'Unknown'),
                                                        "address": place.get('formattedAddress', 'Address not available'),
                                                        "phone": place.get('nationalPhoneNumber', 'Phone not available'),
                                                        "rating": place.get('rating', 'N/A')
                                                    })
                                                    if len(suggestions) >= 5:
                                                        break
                            except Exception as e:
                                pass  # Fallback to mock data
                    
                    # Fallback to mock data if API fails
                    if not suggestions:
                        suggestions = [
                            {"name": "QuickFix Mobiles", "address": "Near your location", "phone": "+91 90000 11111", "rating": "4.2"},
                            {"name": "City Laptop Care", "address": "Electronics repair", "phone": "+91 98888 22222", "rating": "4.5"},
                            {"name": "Green Repair Hub", "address": "Device servicing", "phone": "+91 97777 33333", "rating": "4.0"},
                        ]
                except Exception:
                    suggestions = [
                        {"name": "QuickFix Mobiles", "address": "Near your location", "phone": "+91 90000 11111", "rating": "4.2"},
                        {"name": "City Laptop Care", "address": "Electronics repair", "phone": "+91 98888 22222", "rating": "4.5"},
                    ]
            else:
                # Show mock data as placeholder
                suggestions = [
                    {"name": "Enable location to find nearby shops", "address": "Click 'Use my location' button", "phone": "", "rating": ""},
                ]

    return render(request, 'reuse.html', {
        "recommendation": recommendation, 
        "reasoning": reasoning, 
        "shops": suggestions,
        "needs_location": needs_location,
        "user_lat": user_lat,
        "user_lng": user_lng
    })


# ---------- Urban Mining Value Estimator (no DB) ----------
def value_estimator(request):
    """
    Estimate recoverable metals and INR value using AI for accurate data.
    """
    result = None

    if request.method == 'POST':
        model = (request.POST.get('model') or '').strip()
        age_years = float((request.POST.get('age') or '0').strip() or 0)
        
        # Use AI to get accurate metal content
        prompt = (
            f"For the electronic device '{model}' that is {age_years} years old, "
            f"provide the approximate recoverable precious metals in GRAMS: "
            f"gold, copper, and silver. Also provide current market prices in INR per gram. "
            f"Format your response as: 'Gold: X.XX g, Copper: YY.Y g, Silver: Z.ZZ g. "
            f"Prices: Gold ₹AAAA per g, Copper ₹BB per g, Silver ₹CCC per g.' "
            f"Be specific and accurate for '{model}'."
        )
        ai_response = get_ai_explanation(prompt)
        
        # Parse AI response to extract metal values
        metals = {"gold_g": 0.0, "copper_g": 0.0, "silver_g": 0.0}
        prices = {"gold_g": 7000.0, "copper_g": 0.9, "silver_g": 90.0}
        
        import re
        # Extract gold
        gold_match = re.search(r'Gold[:\s]+([\d.]+)\s*g', ai_response, re.IGNORECASE)
        if gold_match:
            metals["gold_g"] = float(gold_match.group(1))
        gold_price_match = re.search(r'Gold[:\s]+₹?([\d,]+)', ai_response, re.IGNORECASE)
        if gold_price_match:
            prices["gold_g"] = float(gold_price_match.group(1).replace(',', ''))
        
        # Extract copper
        copper_match = re.search(r'Copper[:\s]+([\d.]+)\s*g', ai_response, re.IGNORECASE)
        if copper_match:
            metals["copper_g"] = float(copper_match.group(1))
        copper_price_match = re.search(r'Copper[:\s]+₹?([\d.]+)', ai_response, re.IGNORECASE)
        if copper_price_match:
            prices["copper_g"] = float(copper_price_match.group(1))
        
        # Extract silver
        silver_match = re.search(r'Silver[:\s]+([\d.]+)\s*g', ai_response, re.IGNORECASE)
        if silver_match:
            metals["silver_g"] = float(silver_match.group(1))
        silver_price_match = re.search(r'Silver[:\s]+₹?([\d.]+)', ai_response, re.IGNORECASE)
        if silver_price_match:
            prices["silver_g"] = float(silver_price_match.group(1).replace(',', ''))
        
        # Calculate values
        base_value = sum(metals[k] * prices[k] for k in metals)
        # Apply age depreciation
        depreciation_factor = max(0.3, 1 - (age_years * 0.05))  # 5% per year, min 30%
        payout = base_value * depreciation_factor
        
        result = {
            "model": model, 
            "age_years": age_years, 
            "metals": metals, 
            "prices": prices,
            "base_value": round(base_value, 2), 
            "estimated_payout": round(payout, 2),
            "ai_response": ai_response  # For debugging/display
        }

    return render(request, 'value_estimator.html', {"result": result})


# ---------- Health & Hazard Visualiser (no DB) ----------
def hazard_visualiser(request):
    """
    Explain hazards for a selected component using AI. No DB.
    """
    component = None
    explanation = None
    if request.method == 'POST':
        component = (request.POST.get('component') or '').strip()
        if component:
            # More specific prompt to ensure it's about e-waste components
            prompt = (
                f"Explain how '{component}' as an ELECTRONIC WASTE COMPONENT (from discarded electronics like phones, laptops, TVs) "
                f"can harm the environment and human health when improperly disposed. "
                f"If '{component}' is NOT typically found in e-waste (like paper, plastic bags, etc.), "
                f"clarify that it's not an e-waste component and suggest relevant e-waste components instead. "
                f"Keep response to 3-4 sentences, focusing on soil contamination, water pollution, and health risks in Indian context."
            )
            explanation = get_ai_explanation(prompt)
    return render(request, 'hazard.html', {"component": component, "explanation": explanation})


# ---------- Pickup Scheduling & Community Drive (no DB) ----------
def pickup_scheduling(request):
    """
    Allow users to schedule e-waste pickup or organize community drives.
    Saves submissions to Pickup model for Django admin tracking.
    """
    success = False
    confirmation_data = None
    ai_message = None

    if request.method == 'POST':
        # Collect form data
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()
        waste_type = request.POST.get('waste_type', '').strip()
        drive_type = request.POST.get('drive_type', '').strip()
        pickup_date = request.POST.get('pickup_date', '').strip()
        pickup_time = request.POST.get('pickup_time', '').strip()

        # Save to Pickup model for admin tracking
        Pickup.objects.create(
            name=name,
            email=email,
            phone=phone,
            address=address,
            waste_type=waste_type,
            drive_type=drive_type,
            pickup_date=pickup_date,
            pickup_time=pickup_time,
        )

        confirmation_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'address': address,
            'waste_type': waste_type,
            'drive_type': drive_type,
            'pickup_date': pickup_date,
            'pickup_time': pickup_time,
        }

        success = True
        messages.success(request, "Your request has been saved! We'll contact you soon.")

    return render(request, 'pickup.html', {
        "success": success,
        "confirmation_data": confirmation_data,
    })


# ---------- Kabadiwala & Informal Collector Directory (no DB) ----------
def collectors_directory(request):
    """
    Display verified kabadiwalas/collectors with filters and nomination form.
    Uses static mock data; no database required.
    """
    # Mock collector data (in real app, this could come from a JSON file or DB)
    all_collectors = [
        {"name": "GreenScrap Delhi", "city": "Delhi", "phone": "9999988888", "verified": True},
        {"name": "EcoCycle Mumbai", "city": "Mumbai", "phone": "9898989898", "verified": False},
        {"name": "RecycleHub Bangalore", "city": "Bangalore", "phone": "9777799999", "verified": True},
        {"name": "GreenTech Chennai", "city": "Chennai", "phone": "9666699999", "verified": True},
        {"name": "EcoCollect Pune", "city": "Pune", "phone": "9555599999", "verified": False},
        {"name": "WasteWise Hyderabad", "city": "Hyderabad", "phone": "9444499999", "verified": True},
    ]

    # AI insight on page load
    ai_insight = get_ai_explanation(
        "Generate one short sentence (factual) about how most of India's e-waste is handled informally and why connecting with verified collectors matters."
    )

    # Filter logic
    filtered_collectors = all_collectors
    selected_city = request.GET.get('city', '').strip()
    show_verified_only = request.GET.get('verified_only') == 'on'

    if selected_city:
        filtered_collectors = [c for c in filtered_collectors if c['city'].lower() == selected_city.lower()]
    if show_verified_only:
        filtered_collectors = [c for c in filtered_collectors if c['verified']]

    # Nomination form handling
    nomination_success = False
    if request.method == 'POST' and request.POST.get('action') == 'nominate':
        nominee_name = request.POST.get('nominee_name', '').strip()
        nominee_city = request.POST.get('nominee_city', '').strip()
        nominee_phone = request.POST.get('nominee_phone', '').strip()
        if nominee_name and nominee_city:
            nomination_success = True
            messages.success(request, f"Thank you for nominating {nominee_name}! We'll review and add them if verified.")

    # Get unique cities for dropdown
    unique_cities = sorted(set(c['city'] for c in all_collectors))

    return render(request, 'collectors.html', {
        "collectors": filtered_collectors,
        "all_collectors": all_collectors,
        "unique_cities": unique_cities,
        "selected_city": selected_city,
        "show_verified_only": show_verified_only,
        "ai_insight": ai_insight,
        "nomination_success": nomination_success,
    })


# ---------- Gamified Green Challenges & Badges ----------
def green_challenges(request):
    """
    Display challenges from database; track completion per user when logged in,
    and per-session for anonymous users. Awards badges based on completion count.
    """
    # Fetch active challenges from database
    db_challenges = Challenge.objects.filter(is_active=True)

    # Convert to template-friendly format with stable IDs like "ch{db_id}"
    challenges = [
        {
            "id": f"ch{c.id}",
            "db_id": c.id,
            "title": c.title,
            "co2_saved": c.co2_saved,
        }
        for c in db_challenges
    ]

    # Determine completed set
    if request.user.is_authenticated:
        # Per-user persistence in DB
        user_completed_ids = set(
            f"ch{cc.challenge_id}" for cc in request.user.challenge_completions.all()
        )
    else:
        # Anonymous fallback in session
        user_completed_ids = set(request.session.get('challenges_completed', []))

    # Handle challenge completion
    if request.method == 'POST':
        challenge_id = request.POST.get('challenge_id', '').strip()
        if challenge_id and challenge_id not in user_completed_ids:
            if request.user.is_authenticated:
                # Parse db id from "ch{n}"
                try:
                    db_id = int(challenge_id.replace('ch', ''))
                    ChallengeCompletion.objects.get_or_create(user=request.user, challenge_id=db_id)
                except ValueError:
                    pass  # Ignore malformed IDs silently
            else:
                tmp = list(user_completed_ids)
                tmp.append(challenge_id)
                request.session['challenges_completed'] = tmp
                request.session.modified = True

            user_completed_ids.add(challenge_id)
            challenge_title = next((c['title'] for c in challenges if c['id'] == challenge_id), "challenge")
            messages.success(request, f"Challenge completed: {challenge_title}! 🎉")

    # Compute totals and progress
    total_co2 = sum(c['co2_saved'] for c in challenges if c['id'] in user_completed_ids)
    total_challenges = len(challenges)
    completed_count = len(user_completed_ids)
    progress = int((completed_count / total_challenges) * 100) if total_challenges > 0 else 0

    # Badge logic
    badge = None
    badge_name = None
    if completed_count >= 1:
        badge = "🌱"
        badge_name = "Eco Starter"
    if completed_count >= 3:
        badge = "🌿"
        badge_name = "Green Influencer"
    if completed_count >= 5:
        badge = "🌳"
        badge_name = "Eco Hero"

    return render(request, 'challenges.html', {
        "challenges": challenges,
        "completed": list(user_completed_ids),
        "total_co2": round(total_co2, 1),
        "progress": progress,
        "badge": badge,
        "badge_name": badge_name,
    })


# ---------- Authentication Views ----------

def register_view(request):
    """
    User registration view with validation and success messages.
    """
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '🎉 User successfully created! You can now log in with your credentials.')
            return redirect('register')
        else:
            # Display form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'register.html', {'form': form})


def login_view(request):
    """
    User login view with authentication.
    """
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                # Merge any session-based challenge progress into the user's account
                try:
                    session_completed = request.session.get('challenges_completed', [])
                    if session_completed:
                        migrated = 0
                        for cid in session_completed:
                            try:
                                db_id = int(str(cid).replace('ch', ''))
                            except (ValueError, TypeError):
                                continue
                            _, created = ChallengeCompletion.objects.get_or_create(user=user, challenge_id=db_id)
                            if created:
                                migrated += 1
                        if migrated:
                            messages.info(request, f"We saved {migrated} challenge{'s' if migrated != 1 else ''} from your previous session.")
                        if 'challenges_completed' in request.session:
                            del request.session['challenges_completed']
                            request.session.modified = True
                except Exception:
                    # Don't block login if merge fails
                    pass
                messages.success(request, f'Welcome back, {user.first_name or user.username}! 🌿')
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password. Please try again.')
    else:
        form = UserLoginForm()
    
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    """
    User logout view.
    """
    logout(request)
    messages.success(request, 'You have been logged out successfully. See you soon! 👋')
    return redirect('login')


@login_required
def profile_view(request):
    """
    User profile view with edit capabilities and password change.
    """
    user = request.user
    
    if request.method == 'POST':
        # Check which form was submitted
        if 'update_profile' in request.POST:
            profile_form = UserProfileUpdateForm(request.POST, instance=user)
            password_form = CustomPasswordChangeForm(user)
            
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, '✅ Profile updated successfully!')
                return redirect('profile')
            else:
                for field, errors in profile_form.errors.items():
                    for error in errors:
                        messages.error(request, f'{error}')
        
        elif 'change_password' in request.POST:
            profile_form = UserProfileUpdateForm(instance=user)
            password_form = CustomPasswordChangeForm(user, request.POST)
            
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # Keep user logged in
                messages.success(request, '🔒 Password changed successfully!')
                return redirect('profile')
            else:
                for field, errors in password_form.errors.items():
                    for error in errors:
                        messages.error(request, f'{error}')
    else:
        profile_form = UserProfileUpdateForm(instance=user)
        password_form = CustomPasswordChangeForm(user)
    
    return render(request, 'profile.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'user': user
    })