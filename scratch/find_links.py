import urllib.request
import re
from bs4 import BeautifulSoup

def main():
    url = "https://www.jpx.co.jp/markets/indices/revisions-indices/"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html = response.read().decode("utf-8", errors="ignore")
            
        soup = BeautifulSoup(html, "html.parser")
        
        print("All links on the page:")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if "csv" in href.lower() or "xls" in href.lower() or "浮動株" in text or "比率" in text:
                print(f"Text: {text} | Href: {href}")
                
    except Exception as e:
        print(f"Error fetching page: {e}")

if __name__ == "__main__":
    main()
