from flask import Flask, render_template, request, url_for
import pandas as pd
import folium
from geopy.geocoders import Nominatim
import os
import time

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    map_html = None
    stats = None

    if request.method == "POST":
        file = request.files["file"]
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        df = pd.read_excel(filepath)

        m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
        all_points = []
        failed_rows = []
        success_count = 0
        partial_count = 0
        
        import random
        from geopy.geocoders import ArcGIS

        # Initialize multiple geocoders
        geolocator_osm = Nominatim(user_agent="flask_map_app_v2")
        geolocator_arcgis = ArcGIS()

        def clean_district(name):
            """Remove 'District', 'Jila' etc from name."""
            remove_words = ['jila', 'zila', 'district', 'जिला', 'mandal']
            cleaned = name
            for word in remove_words:
                cleaned = cleaned.replace(word, '').strip()
            return cleaned

        def smart_geocode(row):
            """Try to find location using multiple strategies and providers."""
            raw_loc = row["Full_Location"]
            
            queries_to_try = []
            
            # 1. Full Address
            queries_to_try.append({"q": raw_loc, "exact": True})
            
            # 2. Parsed Components
            try:
                parts = [p.strip() for p in raw_loc.split(',')]
                if len(parts) >= 3:
                    village = parts[0]
                    district_raw = parts[1]
                    state = parts[-2]
                    district = clean_district(district_raw)
                    
                    queries_to_try.append({"q": f"{village}, {district}, {state}", "exact": True})
                    queries_to_try.append({"q": f"{village}, {state}", "exact": True})
            except:
                pass
                
            # EXECUTE PRECISE SEARCHES
            for query_obj in queries_to_try:
                q = query_obj["q"]
                
                # Try ArcGIS (Usually better for India/Hindi)
                try:
                    loc = geolocator_arcgis.geocode(q, timeout=10)
                    if loc: return loc, False
                except: pass
                
                # Try OSM
                try:
                    loc = geolocator_osm.geocode(q, timeout=10)
                    if loc: return loc, False
                except: pass

            # FALLBACK STRATEGY: District Level
            try:
                parts = [p.strip() for p in raw_loc.split(',')]
                if len(parts) >= 3:
                    district = clean_district(parts[1])
                    state = parts[-2]
                    q_fallback = f"{district}, {state}"
                    
                    # Try Fallback on ArcGIS
                    try:
                        loc = geolocator_arcgis.geocode(q_fallback, timeout=10)
                        if loc: return loc, True
                    except: pass
            except: pass
            
            return None, False

        for _, row in df.iterrows():
            try:
                location, is_approximate = smart_geocode(row)
                
                if location:
                    lat = location.latitude
                    lon = location.longitude
                    
                    # If approximate, add jitter to seperate stacked points
                    if is_approximate:
                        lat += random.uniform(-0.01, 0.01)
                        lon += random.uniform(-0.01, 0.01)
                        partial_count += 1
                        color = "orange"
                        popup_warning = "<br><b style='color:orange'>(Approximate Location)</b>"
                    else:
                        success_count += 1
                        # Determine styling based on type
                        is_origin = str(row["Type"]).strip().lower() == "origin"
                        color = "red" if is_origin else "blue"
                        popup_warning = ""

                    all_points.append([lat, lon])
                    
                    icon_type = "star" if str(row["Type"]).strip().lower() == "origin" else "map-marker"
                    label_text = row["Label"] if "Label" in row else row["Village"]

                    folium.Marker(
                        location=[lat, lon],
                        popup=folium.Popup(f"""
                        <div style="width: 200px">
                            <h4 style="margin-bottom: 5px; color: {color}">{row['Village']}</h4>
                            <b>Families:</b> {row['Families']}<br>
                            <b>Type:</b> {row['Type']}
                            {popup_warning}
                        </div>
                        """, max_width=300),
                        tooltip=str(label_text),
                        icon=folium.Icon(color=color, icon=icon_type, prefix='fa')
                    ).add_to(m)
                else:
                    failed_rows.append(row["Village"])

                # Gentle rate limiting
                time.sleep(0.5)
            except Exception as e:
                print(f"Error processing row: {e}")
                failed_rows.append(f"Row Error: {e}")
                continue

        if all_points:
            m.fit_bounds(all_points)
        
        map_path = os.path.join("static", "map.html")
        m.save(map_path)

        map_html = url_for('static', filename='map.html')
        
        stats = {
            "success": success_count,
            "partial": partial_count,
            "failed": len(failed_rows),
            "failed_list": failed_rows
        }

    return render_template("index.html", map_html=map_html, stats=stats)



if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
