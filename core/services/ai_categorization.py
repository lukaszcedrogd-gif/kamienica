import requests
import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Konfiguracja Ollama
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "neural-chat"  # lub "mistral"

# Mapowanie kategorii na ludzkie nazwy
CATEGORY_DISPLAY_MAP = {
    'czynsz': 'Czynsz',
    'oplaty': 'Opłaty',
    'oplata_bankowa': 'Opłata bankowa',
    'energia_klatka': 'Energia klatka',
    'energia_m8': 'Energia M8',
    'na_potrzeby_kamienicy': 'Na potrzeby kamienicy',
    'naprawy_remonty': 'Naprawy/remonty',
    'oplata_za_wode': 'Opłata za wodę',
    'wywoz_smieci': 'Wywóz śmieci',
    'sprzatanie': 'Sprzątanie',
    'ogrodnik': 'Ogrodnik',
    'ubezpieczenie': 'Ubezpieczenie',
    'internet_telefon': 'Internet/telefon',
    'elektryk': 'Elektryk',
    'kominiarz': 'Kominiarz',
    'piece_co': 'Piece CO',
    'podatek': 'Podatek',
    'oplata_nie_stanowiaca_kosztu': 'Opłata nie stanowiąca kosztu',
}


def categorize_with_ai(
    description: str,
    contractor: str = "",
    amount: float = 0,
    timeout: int = 30
) -> Tuple[Optional[str], str, str]:
    """
    Kategoryzuje transakcję przy pomocy lokalnego modelu AI (Ollama).
    
    Args:
        description: Opis transakcji
        contractor: Kontrahent
        amount: Kwota transakcji
        timeout: Timeout dla żądania (sekundy)
    
    Returns:
        Tuple: (category_code, status, log_message)
        - category_code: Kod kategorii lub None
        - status: "PROCESSED" / "UNPROCESSED" / "ERROR"
        - log_message: Wiadomość dla logu
    """
    
    try:
        categories_list = ", ".join([f"{k} ({v})" for k, v in CATEGORY_DISPLAY_MAP.items()])
        
        prompt = f"""Przeanalizuj następującą transakcję finansową i przypisz jej najlepszą kategorię.

Opis: {description}
Kontrahent: {contractor}
Kwota: {amount} PLN

Dostępne kategorie:
{categories_list}

Zwróć TYLKO kod kategorii (np. 'czynsz', 'energia_klatka', itp.) bez żadnych dodatkowych wyjaśnień.
Jeśli nie potrafisz jednoznacznie przypisać kategorii, odpowiedz: UNKNOWN"""

        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.3,  # Niższa temperatura = mniej kreatywne, bardziej skupione
            },
            timeout=timeout
        )
        
        if response.status_code != 200:
            logger.warning(f"Ollama API error: {response.status_code}")
            return None, "ERROR", f"Błąd API Ollama: {response.status_code}"
        
        result = response.json()
        ai_response = result.get("response", "").strip().lower()
        
        # Sprawdzenie czy odpowiedź zawiera kod kategorii
        if ai_response == "unknown":
            log_msg = f"AI nie potrafił kategoryzować transakcji. Opis: {description[:50]}..."
            return None, "UNPROCESSED", log_msg
        
        # Walidacja kodu kategorii
        if ai_response not in CATEGORY_DISPLAY_MAP:
            # Spróbuj dopasować do istniejącej kategorii
            for code in CATEGORY_DISPLAY_MAP.keys():
                if code in ai_response:
                    log_msg = f"AI kategoryzacja (ścieżka): {CATEGORY_DISPLAY_MAP[code]}"
                    return code, "PROCESSED", log_msg
            
            log_msg = f"AI zwrócił nieznaną kategorię: '{ai_response}'"
            return None, "UNPROCESSED", log_msg
        
        log_msg = f"AI kategoryzacja: {CATEGORY_DISPLAY_MAP[ai_response]}"
        return ai_response, "PROCESSED", log_msg
        
    except requests.exceptions.ConnectionError:
        logger.error("Nie można połączyć się z Ollama na localhost:11434")
        return None, "ERROR", "Ollama niedostępna. Upewnij się że działa: ollama serve"
    except requests.exceptions.Timeout:
        logger.error(f"Timeout Ollama (>{timeout}s)")
        return None, "ERROR", f"Timeout AI ({timeout}s)"
    except json.JSONDecodeError as e:
        logger.error(f"Błąd parsowania JSON od Ollama: {e}")
        return None, "ERROR", f"Błąd parsowania odpowiedzi Ollama: {e}"
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd AI: {e}")
        return None, "ERROR", f"Nieoczekiwany błąd: {str(e)}"


def test_ollama_connection() -> bool:
    """
    Testuje dostępność Ollama API.
    """
    try:
        response = requests.get(f"{OLLAMA_API_URL.replace('/api/generate', '')}/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False
