# app/core/llm.py
from typing import Optional, Dict, Any
from app.core.config import settings # Importa la instancia única de settings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
# Quitar imports específicos de HF aquí, se manejarán en su función
# from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline
# from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import logging
import torch # Necesario para HF local

logger = logging.getLogger(__name__)

# Variable para el cliente LLM (singleton)
_llm_client: Optional[BaseChatModel] = None

# # --- Función de Inicialización Específica para HF Local ---
# # (Mantenemos esta separada para claridad)
# def _initialize_local_hf_llm() -> Optional[BaseChatModel]:
#     """Inicializa y devuelve un LLM local usando HuggingFacePipeline."""
#     # Importaciones específicas de HF solo cuando se necesitan
#     try:
#         from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline
#         from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, BitsAndBytesConfig
#     except ImportError as e:
#         logger.error(f"Faltan dependencias para Hugging Face local: {e}. Instala: pip install transformers accelerate bitsandbytes torch")
#         return None

#     model_id = settings.HUGGINGFACE_MODEL_ID
#     device_setting = settings.HF_MODEL_DEVICE
#     load_in_8bit = settings.HF_MODEL_LOAD_IN_8BIT
#     load_in_4bit = settings.HF_MODEL_LOAD_IN_4BIT
#     if load_in_4bit: load_in_8bit = False # 4bit tiene precedencia

#     logger.info(f"Iniciando carga de modelo local HF: {model_id}")

#     # Determinar dispositivo
#     if device_setting == "auto":
#         device = "cuda" if torch.cuda.is_available() else "cpu"
#         if device == "cpu":
#                 try:
#                     if torch.backends.mps.is_available(): device = "mps"
#                 except AttributeError: pass
#     else:
#         device = device_setting
#     logger.info(f"  Dispositivo seleccionado: {device}")

#     # Configurar cuantización
#     quantization_config = None
#     bnb_config = None
#     if load_in_8bit or load_in_4bit:
#         try:
#             import bitsandbytes
#             logger.info(f"  Aplicando cuantización: 8bit={load_in_8bit}, 4bit={load_in_4bit}")
#             if load_in_4bit:
#                 bnb_config = BitsAndBytesConfig(
#                     load_in_4bit=True,
#                     bnb_4bit_quant_type="nf4",
#                     bnb_4bit_compute_dtype=torch.bfloat16, # O float16 según tu GPU
#                     # bnb_4bit_use_double_quant=True, # Opcional
#                     # bnb_4bit_quant_storage=... # Opcional
#                 )
#                 quantization_config = {"quantization_config": bnb_config}
#             elif load_in_8bit:
#                  quantization_config = {"load_in_8bit": True}

#         except ImportError:
#             logger.error("  Se solicitó cuantización pero 'bitsandbytes' no está instalado. Ignorando.")
#             quantization_config = {}
#         except Exception as q_err:
#                 logger.error(f"  Error configurando cuantización: {q_err}. Ignorando.")
#                 quantization_config = {}
#     else:
#          quantization_config = {}


#     try:
#         logger.info(f"  Cargando tokenizer: {model_id}")
#         tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=settings.HF_CACHE_FOLDER)
#         if tokenizer.pad_token is None:
#             tokenizer.pad_token = tokenizer.eos_token
#             logger.info("  Tokenizer: pad_token establecido a eos_token.")

#         logger.info(f"  Cargando modelo: {model_id}. Esto puede tardar y consumir RAM/VRAM...")
#         # Determinar dtype y device_map
#         torch_dtype = torch.float16 if device == "cuda" else torch.float32
#         # device_map es mejor con cuantización o múltiples GPUs
#         use_device_map = "auto" if (quantization_config or device == "cuda") else None

#         model_kwargs_load = {
#             "cache_dir": settings.HF_CACHE_FOLDER,
#             "torch_dtype": torch_dtype,
#             "trust_remote_code": True, # Revisar si tu modelo lo requiere
#             **quantization_config
#         }
#         if use_device_map:
#             model_kwargs_load["device_map"] = use_device_map
#             logger.info(f"  Usando device_map='{use_device_map}'")


#         model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs_load)

#         # Mover a dispositivo si no se usó device_map y no está cuantizado
#         if not use_device_map and not quantization_config:
#              model.to(device)
#              logger.info(f"  Modelo movido manualmente a: {device}")

#         logger.info("  Modelo cargado. Creando pipeline de Transformers...")
#         # Ajustar task si es necesario (text-generation es común para instruct)
#         pipe = pipeline(
#             "text-generation",
#             model=model,
#             tokenizer=tokenizer,
#             max_new_tokens=512, # Hacer configurable?
#             temperature=0.2,    # Hacer configurable?
#             top_p=0.95,
#             repetition_penalty=1.1,
#             # device=0 if device=="cuda" else -1 # A veces necesario si device_map no funciona bien
#         )

#         logger.info("  Envolviendo pipeline en HuggingFacePipeline de LangChain...")
#         # NOTA: HuggingFacePipeline es técnicamente un LLM, no un ChatModel.
#         # Langchain intenta hacerlo funcionar como ChatModel, pero puede tener limitaciones.
#         # Para una mejor experiencia de chat, podrías necesitar un wrapper adicional o
#         # usar modelos específicamente diseñados para la interfaz de chat de Transformers.
#         hf_pipeline = HuggingFacePipeline(pipeline=pipe)

#         logger.info("LLM local HuggingFacePipeline inicializado.")
#         return hf_pipeline

#     except Exception as e:
#         logger.exception(f"Error fatal al cargar o inicializar el modelo local HF '{model_id}': {e}")
#         return None


# --- Función Principal para Obtener el LLM ---
def get_llm(force_reload: bool = False) -> Optional[BaseChatModel]:
    """
    Obtiene la instancia configurada del ChatModel (o LLM compatible)
    basado en settings.LLM_PROVIDER. Implementa un patrón singleton.
    """
    global _llm_client
    if _llm_client is not None and not force_reload:
        return _llm_client

    provider = settings.LLM_PROVIDER.lower()
    logger.info(f"Intentando obtener LLM para el proveedor: {provider}")

    initialized_llm = None
    try:
        if provider == "google":
            if not settings.GEMINI_API_KEY:
                logger.error("GEMINI_API_KEY no configurada.")
                raise ValueError("API Key de Gemini no encontrada.")
            initialized_llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL_NAME,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.1,
                convert_system_message_to_human=True
            )
            logger.info(f"ChatGoogleGenerativeAI ({settings.GEMINI_MODEL_NAME}) inicializado.")

        elif provider == "openai":
            if not settings.OPENAI_API_KEY:
                logger.error("OPENAI_API_KEY no configurada.")
                raise ValueError("API Key de OpenAI no encontrada.")
            initialized_llm = ChatOpenAI(
                model=settings.OPENAI_MODEL_NAME,
                api_key=settings.OPENAI_API_KEY,
                temperature=0.1
            )
            logger.info(f"ChatOpenAI ({settings.OPENAI_MODEL_NAME}) inicializado.")

        # elif provider == "huggingface_local":
        #     initialized_llm = _initialize_local_hf_llm()
        #     if initialized_llm:
        #          logger.info(f"HuggingFace Local LLM ({settings.HUGGINGFACE_MODEL_ID}) inicializado.")
        #     else:
        #          logger.error("Fallo al inicializar el modelo local de Hugging Face.")
        #          raise RuntimeError("No se pudo inicializar el LLM local de Hugging Face.")


        else:
            logger.error(f"Proveedor LLM desconocido o no soportado: '{provider}'.")
            raise ValueError(f"Proveedor LLM no válido: {provider}")

        _llm_client = initialized_llm # Almacenar en caché global
        return _llm_client

    except Exception as e:
        logger.exception(f"Error fatal durante la inicialización del LLM para el proveedor '{provider}': {e}")
        _llm_client = None
        return None