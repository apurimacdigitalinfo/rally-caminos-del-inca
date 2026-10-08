import asyncio
import json
import re
from playwright.async_api import async_playwright

URL_EXEC = "https://script.google.com/macros/s/AKfycbx7JxA1xQx9kJzD6-67g2Fq98lMYry15weEMwkm1e20pEl94DJ9tEUlMRIUfuwPzRdX/exec"
ARCHIVO_SALIDA = "clasificacion_caminos_del_inca.json"


async def extraer_y_guardar_clasificacion():
    print("🔍 Iniciando extracción de tiempos desde el endpoint de Google...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        datos_crudos = []

        # Interceptar la matriz de datos directo desde la red (JSON RPC de Google)
        async def interceptar_red(response):
            try:
                if (
                    "script.google" in response.url
                    or "googleusercontent" in response.url
                ):
                    text = await response.text()
                    if "op.exec" in text:
                        datos_crudos.append(text)
            except Exception:
                pass

        page.on("response", interceptar_red)

        await page.goto(URL_EXEC, wait_until="networkidle")
        await page.wait_for_timeout(5000)

        autos = []

        # -------------------------------------------------------------
        # 1. EXTRACCIÓN DESDE EL PAYLOAD INTERCEPTADO (100% Preciso)
        # -------------------------------------------------------------
        if datos_crudos:
            for payload in datos_crudos:
                clean_payload = re.sub(r"^\)\]\}'\s*", "", payload)
                try:
                    data = json.loads(clean_payload)
                    for item in data:
                        if (
                            isinstance(item, list)
                            and len(item) > 1
                            and item[0] == "op.exec"
                        ):
                            matriz_str = item[1][1]
                            matriz = json.loads(matriz_str)

                            for fila in matriz:
                                if len(fila) >= 23:
                                    pos = fila[18]
                                    num = fila[19]
                                    tripulacion = fila[20].replace("\n", " ").strip()
                                    categoria = fila[21]
                                    tiempo = fila[22]

                                    if pos and str(pos).isdigit():
                                        autos.append(
                                            {
                                                "posicion": int(pos),
                                                "numero": str(num),
                                                "tripulacion": tripulacion,
                                                "categoria": categoria,
                                                "tiempo": tiempo,
                                            }
                                        )
                except Exception:
                    pass

        # Ordenar resultados por posición numérica
        if autos:
            autos = sorted(autos, key=lambda x: x["posicion"])

        # -------------------------------------------------------------
        # 2. FALLBACK DESDE EL DOM HTML (Si la interceptación falla)
        # -------------------------------------------------------------
        if not autos:
            target_frame = None
            for frame in page.frames:
                txt = await frame.inner_text("body")
                if "Tripulacion" in txt or "Orden" in txt:
                    target_frame = frame
                    break

            if target_frame:
                await target_frame.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
                await page.wait_for_timeout(1000)

                filas = await target_frame.query_selector_all("tr")
                for fila in filas:
                    celdas = await fila.query_selector_all("td")
                    textos = [(await c.inner_text()).strip() for c in celdas]

                    if len(textos) >= 3 and textos[0].isdigit():
                        autos.append(
                            {
                                "posicion": int(textos[0]),
                                "numero": textos[1],
                                "tripulacion": textos[2].replace("\n", " ").strip(),
                                "categoria": textos[3] if len(textos) > 3 else "",
                                "tiempo": textos[4] if len(textos) > 4 else "",
                            }
                        )

        await browser.close()

        # -------------------------------------------------------------
        # 3. GUARDAR RESULTADOS EN ARCHIVO JSON
        # -------------------------------------------------------------
        if autos:
            with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
                json.dump(autos, f, indent=2, ensure_ascii=False)
            print(f"✅ ¡Éxito! Se extrajeron {len(autos)} vehículos.")
            print(f"📁 Datos guardados correctamente en '{ARCHIVO_SALIDA}'.")
        else:
            print("❌ No se lograron extraer los datos de la carrera.")

        return autos


if __name__ == "__main__":
    asyncio.run(extraer_y_guardar_clasificacion())