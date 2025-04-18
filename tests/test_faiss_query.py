import os
import pprint
import torch
from typing import List, Tuple, Optional, Dict, Any # Mejores type hints

# --- Dependencias Actualizadas ---
# Asegúrate de instalar: pip install langchain faiss-cpu sentence-transformers torch langchain-huggingface
from langchain_community.vectorstores import FAISS
# ¡Importación actualizada para evitar deprecación!
from langchain_huggingface import HuggingFaceEmbeddings

# --- Configuración (Mantener en un solo lugar) ---
VECTOR_STORE_FOLDER = "vector_store_index"
VECTOR_STORE_INDEX_NAME = "data_index" # Asegúrate que este sea el nombre correcto
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Carpeta para descargar modelos de HuggingFace (opcional pero recomendado)
HF_CACHE_FOLDER = "./huggingface_cache"

# Configuración del Modelo de Embeddings (Consistencia es CLAVE)
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
# Asegúrate que esto coincida con cómo creaste el índice
NORMALIZE_EMBEDDINGS = True # O False si así lo creaste

# --- Fin Configuración ---

def load_embeddings_model() -> Optional[HuggingFaceEmbeddings]:
    """Carga el modelo de embeddings especificado usando langchain-huggingface."""
    print(f"Cargando modelo de embeddings: {EMBEDDING_MODEL_NAME} en dispositivo {DEVICE}...")
    model_kwargs = {'device': DEVICE}
    encode_kwargs = {'normalize_embeddings': NORMALIZE_EMBEDDINGS}
    try:
        # Usando la clase actualizada
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs,
            cache_folder=HF_CACHE_FOLDER
        )
        print("Modelo de embeddings cargado exitosamente.")
        return embeddings
    except Exception as e:
        print(f"Error fatal al cargar el modelo de embeddings: {e}")
        # Considera si quieres propagar el error o simplemente devolver None
        # raise e
        return None

def load_vector_store(embeddings: HuggingFaceEmbeddings) -> Optional[FAISS]:
    """Carga el índice FAISS local."""
    faiss_file_path = os.path.join(VECTOR_STORE_FOLDER, f"{VECTOR_STORE_INDEX_NAME}.faiss")
    pkl_file_path = os.path.join(VECTOR_STORE_FOLDER, f"{VECTOR_STORE_INDEX_NAME}.pkl")

    print(f"\nIntentando cargar índice FAISS desde: {VECTOR_STORE_FOLDER}/{VECTOR_STORE_INDEX_NAME}")

    if not os.path.exists(faiss_file_path) or not os.path.exists(pkl_file_path):
        print("--- ERROR ---")
        print("No se encontraron los archivos .faiss o .pkl en la ruta especificada.")
        print(f"Verifica que la carpeta '{VECTOR_STORE_FOLDER}' y los archivos")
        print(f"'{VECTOR_STORE_INDEX_NAME}.faiss' y '{VECTOR_STORE_INDEX_NAME}.pkl' existan.")
        return None

    try:
        print("Cargando índice local FAISS...")
        vector_store = FAISS.load_local(
            folder_path=VECTOR_STORE_FOLDER,
            embeddings=embeddings,
            index_name=VECTOR_STORE_INDEX_NAME,
            allow_dangerous_deserialization=True # Necesario para PKL, seguro si confías en el origen
        )
        print("¡Índice FAISS cargado exitosamente!")
        return vector_store
    except ModuleNotFoundError as e:
        print(f"--- ERROR de Módulo al cargar FAISS ---: {e}")
        print("Asegúrate de tener instaladas las mismas librerías que usaste en Colab (pandas, numpy, etc.).")
        return None
    except Exception as e:
        print(f"--- ERROR inesperado al cargar el índice FAISS ---: {e}")
        return None

def filter_results_by_metadata(
    results_with_scores: List[Tuple[Any, float]],
    filter_criteria: Dict[str, Any]
) -> List[Tuple[Any, float]]:
    """
    Filtra una lista de resultados (documento, score) basada en metadatos.
    NOTA: Este es un filtrado POST-recuperación.
    """
    if not filter_criteria:
        return results_with_scores

    filtered_results = []
    print(f"Filtrando resultados con: {filter_criteria}")
    for doc, score in results_with_scores:
        metadata = doc.metadata
        match = True
        for key, value in filter_criteria.items():
            # Comprobar si la clave existe y si el valor coincide (convirtiendo a string para comparar)
            if key not in metadata or str(metadata.get(key)) != str(value):
                match = False
                break
        if match:
            filtered_results.append((doc, score))

    print(f"Resultados después del filtrado: {len(filtered_results)}")
    return filtered_results


def test_query(
    vector_store: FAISS,
    query: str,
    k: int = 10,
    search_type: str = "similarity",
    filter_metadata: Optional[Dict[str, Any]] = None
):
    """
    Ejecuta una búsqueda en el vector store con opciones y muestra los resultados.

    Args:
        vector_store: La instancia cargada de FAISS.
        query: La consulta del usuario.
        k: El número de resultados a recuperar *inicialmente*.
        search_type: 'similarity' (búsqueda estándar) o 'mmr' (Maximum Marginal Relevance).
        filter_metadata: Un diccionario para filtrar resultados por metadatos (post-recuperación).
                         Ejemplo: {"master_role": "cap.", "news_section": "E"}
    """
    if not vector_store:
        print("El índice FAISS no está cargado. No se puede realizar la búsqueda.")
        return

    print(f"\n--- Ejecutando Búsqueda ---")
    print(f"Consulta: '{query}'")
    print(f"Método: {search_type}")
    print(f"Resultados iniciales a buscar (k): {k}")
    if filter_metadata:
        print(f"Filtro Post-Búsqueda: {filter_metadata}")

    results_with_scores = []
    try:
        if search_type == "similarity":
            results_with_scores = vector_store.similarity_search_with_score(query, k=k)
        elif search_type == "mmr":
            # MMR busca diversidad. fetch_k recupera más documentos inicialmente para la selección.
            fetch_k = max(k * 5, 20) # Recuperar más candidatos para MMR
            print(f"MMR fetch_k (candidatos iniciales): {fetch_k}")
            results_with_scores = vector_store.max_marginal_relevance_search_with_score(
                query, k=k, fetch_k=fetch_k
            )
        else:
            print(f"Error: Tipo de búsqueda '{search_type}' no soportado. Usa 'similarity' o 'mmr'.")
            return

        print(f"\n--- Resultados Recuperados ({len(results_with_scores)}) ---")

        # Aplicar filtrado post-recuperación si se especificó
        if filter_metadata:
            final_results = filter_results_by_metadata(results_with_scores, filter_metadata)
        else:
            final_results = results_with_scores

        print(f"\n--- Resultados Finales a Mostrar ({len(final_results)}) ---")

        if not final_results:
            print("No se encontraron resultados que coincidan con la consulta" + (" y el filtro." if filter_metadata else "."))
            return

        # Mostrar solo hasta k resultados finales (por si el filtro redujo mucho)
        for i, (doc, score) in enumerate(final_results[:k]):
            print(f"\nResultado #{i+1} (Score: {score:.4f}):")
            print("-" * 20)
            print("Contenido (parsed_text):")
            print(doc.page_content)
            print("\nMetadatos:")
            pprint.pprint(doc.metadata, indent=2)
            print("-" * 20)
        if len(final_results) > k:
            print(f"... ({len(final_results) - k} resultados más encontrados pero no mostrados)")


    except Exception as e:
        print(f"\n--- ERROR durante la búsqueda ---: {e}")
        # Considera añadir traceback para más detalles en caso de error inesperado
        # import traceback
        # traceback.print_exc()

# --- Ejecución Principal ---
if __name__ == "__main__":
    print("--- Iniciando Test de Consulta FAISS (Mejorado) ---")

    # 1. Cargar modelo de embeddings
    embeddings_model = load_embeddings_model()

    if not embeddings_model:
        print("Fallo al cargar el modelo de embeddings. Abortando.")
    else:
        # 2. Cargar el índice FAISS
        faiss_db = load_vector_store(embeddings_model)

        if not faiss_db:
            print("\nNo se pudo cargar el índice FAISS, la prueba de consulta no se ejecutará.")
        else:
            # 3. --- Parámetros de la Prueba (Modifica aquí) ---
            test_query_text: str = "información sobre el capitán Litlejohn"
            number_of_results: int = 10      # Cuántos resultados finales mostrar como máximo
            search_method: str = "similarity" # Opciones: "similarity", "mmr"
            metadata_filter: Optional[Dict[str, Any]] = None # Sin filtro
            # Ejemplo de filtro: {"master_role": "cap.", "travel_departure_port": "New-York"}
            # metadata_filter: Dict[str, Any] = {"master_name": "Litlejohn"} # Filtro específico


            # --- Ejecutar la consulta de prueba ---
            test_query(
                vector_store=faiss_db,
                query=test_query_text,
                k=number_of_results,
                search_type=search_method,
                filter_metadata=metadata_filter
            )

    print("\n--- Fin del Test ---")