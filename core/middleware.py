import requests
import threading
from math import radians, sin, cos, sqrt, atan2

BITS_CAMPUSES = {
    'GOA': (15.3911442733276, 73.87815086678745),
    'HYD': (17.544822002003123, 78.57271655444397),
    'PIL': (28.359229729445914, 75.58816379595879),
    'DUB': (25.131566983306616, 55.4200293516723),
}

HEADERS = {"User-Agent": "Mozilla/5.0 (BITSGeolocator/1.0)"}


class CampusDetectorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_data = request.session.get('user_data')
        if user_data:
            email = user_data.get('email')
            if email:
                from core.models import Person, Campus
                person = Person.objects.filter(email=email).first()
                ip = self._get_client_ip(request)

                if person is not None and person.campus == Campus.OTHERS:
                    campus = self._get_nearest_campus_from_ip(ip)
                    if campus != 'OTH':
                        person.campus = campus
                        person.save()
                else:
                    threading.Thread(
                        target=self._get_nearest_campus_from_ip,
                        args=(ip,),
                        daemon=True,
                    ).start()

        return self.get_response(request)

    def _get_client_ip(self, request):
        return (
            request.META.get('HTTP_CF_CONNECTING_IP')
            or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR')
        )

    def _get_nearest_campus_from_ip(self, ip):
        lat, lon = self._get_location(ip)
        return self._get_nearest_campus(lat, lon)

    def _get_location(self, ip):
        try:
            url = f"https://api.ipregistry.co/{ip}?key=tryout"
            res = requests.get(url, headers=HEADERS, timeout=2).json()
            loc = res.get("location", {})
            return float(loc.get("latitude")), float(loc.get("longitude"))
        except Exception:
            return self._get_location2(ip)

    def _get_location2(self, ip):
        try:
            url = f"https://ipinfo.io/{ip}/json"
            res = requests.get(url, headers=HEADERS, timeout=2).json()
            if "loc" in res:
                lat_str, lon_str = res["loc"].split(",")
                return float(lat_str), float(lon_str)
            return self._get_location3(ip)
        except Exception:
            return self._get_location3(ip)

    def _get_location3(self, ip):
        try:
            url = f"https://ipdata.co/{ip}?api-key=test"
            res = requests.get(url, headers=HEADERS, timeout=2).json()
            return float(res.get("latitude")), float(res.get("longitude"))
        except Exception:
            return self._get_location4(ip)

    def _get_location4(self, ip):
        try:
            url = f"http://ip-api.com/json/{ip}"
            res = requests.get(url, headers=HEADERS, timeout=2).json()
            return float(res.get("lat")), float(res.get("lon"))
        except Exception:
            return None, None

    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    def _get_nearest_campus(self, lat, lon):
        if lat is None or lon is None:
            return 'OTH'
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return 'OTH'

        min_dist = float('inf')
        nearest = 'OTH'
        for campus, (clat, clon) in BITS_CAMPUSES.items():
            dist = self._haversine(lat, lon, clat, clon)
            if dist < min_dist:
                min_dist = dist
                nearest = campus
        return nearest
