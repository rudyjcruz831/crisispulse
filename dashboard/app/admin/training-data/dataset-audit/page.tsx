"use client";

import "./dataset-audit.css";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { defineMessages, formatMessage, LanguageSwitcher, useLocale } from "../../../i18n";

const messages = defineMessages({
  documentTitle: "External Dataset Audit — CrisisPulse",
  documentDescription: "Check rights, content, and label compatibility before training CrisisPulse with external data.",
  brandHome: "CrisisPulse dashboard home",
  primaryNavigation: "Primary navigation",
  dashboard: "Dashboard",
  admin: "Admin",
  trainingData: "Training data",
  audit: "Dataset audit",
  eyebrow: "External data safety check",
  heroTitle: "Before we train, prove every dataset is safe and useful.",
  heroDescription: "An online dataset can be free to download and still be unusable for our classifier. This page answers four plain questions before a large file enters CrisisPulse.",
  backToTraining: "Back to training data",
  refresh: "Refresh audit",
  refreshing: "Refreshing…",
  registerLoadedAt: "Register loaded {time}",
  evidenceReviewed: "Evidence reviewed {date}",
  registerLoaded: "Audit register loaded",
  checkingAudit: "Loading audit register",
  staleAudit: "Showing saved audit — refresh failed",
  auditUnavailable: "Audit unavailable",
  refreshFailed: "The saved audit remains visible, but the latest refresh failed. No decision was changed.",
  fourChecks: "The four checks",
  fourChecksHeading: "What “dataset audit” means in plain English.",
  fourChecksDescription: "A source must pass all classifier requirements. A useful flood map can still be the wrong material for teaching an article model.",
  rightsTitle: "May we use it?",
  rightsHelp: "Confirm the exact license permits local model training and the way we plan to use the result.",
  contentTitle: "Does it contain article words?",
  contentHelp: "Our classifier needs the same kind of headline or article text it will receive after launch.",
  labelsTitle: "What do its labels mean?",
  labelsHelp: "Flood event, warning, heavy rain, and unrelated news are different answers—not interchangeable names.",
  separationTitle: "Can we keep the test honest?",
  separationHelp: "Imported examples stay marked by source, and newer CrisisPulse articles remain untouched for final testing.",
  summaryEyebrow: "Current decision",
  summaryHeading: "Useful outside data exists, but none is a drop-in replacement for your labels.",
  sourceCount: "Sources checked",
  trainingApproved: "Approved for direct training",
  supportOnly: "Support or research only",
  blocked: "Blocked from training",
  largeDownloads: "Large files downloaded",
  zeroDownloads: "0",
  zeroDownloadsHelp: "Only public descriptions and small metadata records were inspected.",
  sourceCountHelp: "Each source keeps its own evidence and decision.",
  trainingApprovedHelp: "Requires approved rights, compatible text, and compatible labels.",
  supportOnlyHelp: "May help validate events or future research without becoming a classifier row.",
  blockedHelp: "Unknown rights or incompatible material stays outside the model.",
  candidates: "Candidate datasets",
  candidatesHeading: "See exactly why each source can—or cannot—train the article classifier.",
  candidatesDescription: "No outside label is silently converted into a CrisisPulse answer. Unknown means blocked until evidence resolves it.",
  license: "Rights",
  articleText: "Article text",
  labelFit: "Label fit",
  access: "Access",
  finalUse: "CrisisPulse decision",
  trainingDecision: "Training",
  importDecision: "Import",
  approved: "Approved",
  blockedStatus: "Blocked",
  directFit: "Direct fit",
  partialFit: "Partial fit",
  incompatible: "Not compatible",
  unknown: "Unknown",
  available: "Available",
  unavailable: "Not included",
  openSource: "Open official source",
  labelCrosswalk: "Label crosswalk",
  sourceLabel: "Source label",
  crisisPulseLabel: "CrisisPulse label",
  use: "How it may be used",
  noDirectMapping: "No safe direct mapping documented",
  evidence: "Evidence checked",
  notes: "Important notes",
  loadingHeading: "Checking the external dataset register…",
  loadingHelp: "No large files are being downloaded and no training job is starting.",
  errorHeading: "The dataset audit could not be loaded.",
  errorHelp: "Make sure the local CrisisPulse API is running, then try again. No data or model was changed.",
  retry: "Try again",
  emptyHeading: "No external datasets are registered yet.",
  emptyHelp: "The audit register is empty; outside data remains blocked by default.",
  nextEyebrow: "What happens next",
  nextHeading: "Build the training engine now; admit data only after it passes.",
  nextDescription: "This keeps momentum without producing a model that looks impressive but learned the wrong lesson.",
  nextOne: "Keep native reviews as the trusted four-class core",
  nextOneHelp: "Your labels teach the exact distinctions CrisisPulse must make.",
  nextTwo: "Use compatible external labels with permanent provenance",
  nextTwoHelp: "Every imported row records where it came from, its original label, license, and conversion rule.",
  nextThree: "Run a CPU baseline before the RTX 4070",
  nextThreeHelp: "A fast baseline proves that the data and split work before a larger local experiment.",
  nextFour: "Protect a newer native holdout",
  nextFourHelp: "The final test uses articles the model never saw, separated by time, publisher, and story.",
  policyTitle: "Safe default",
  policyHelp: "Unknown license = blocked. External labels are not treated as human CrisisPulse ground truth. A native holdout is always required.",
  readOnly: "Read-only audit",
  readOnlyHelp: "This screen cannot download datasets, start training, deploy a model, or alter reviews.",
  footerHome: "CrisisPulse admin",
}, {
  documentTitle: "Auditoría de datos externos — CrisisPulse",
  documentDescription: "Compruebe derechos, contenido y compatibilidad de etiquetas antes de entrenar CrisisPulse con datos externos.",
  brandHome: "Inicio del panel de CrisisPulse",
  primaryNavigation: "Navegación principal",
  dashboard: "Panel",
  admin: "Administración",
  trainingData: "Datos de entrenamiento",
  audit: "Auditoría de datos",
  eyebrow: "Comprobación de seguridad de datos externos",
  heroTitle: "Antes de entrenar, demostremos que cada conjunto es seguro y útil.",
  heroDescription: "Un conjunto en línea puede ser gratuito para descargar y aun así no servir para nuestro clasificador. Esta página responde cuatro preguntas sencillas antes de que un archivo grande entre en CrisisPulse.",
  backToTraining: "Volver a datos de entrenamiento",
  refresh: "Actualizar auditoría",
  refreshing: "Actualizando…",
  registerLoadedAt: "Registro cargado {time}",
  evidenceReviewed: "Evidencia revisada {date}",
  registerLoaded: "Registro de auditoría cargado",
  checkingAudit: "Cargando registro de auditoría",
  staleAudit: "Mostrando auditoría guardada — falló la actualización",
  auditUnavailable: "Auditoría no disponible",
  refreshFailed: "La auditoría guardada sigue visible, pero falló la actualización. No cambió ninguna decisión.",
  fourChecks: "Las cuatro comprobaciones",
  fourChecksHeading: "Qué significa “auditoría de datos” en palabras sencillas.",
  fourChecksDescription: "Una fuente debe aprobar todos los requisitos del clasificador. Un mapa de inundaciones útil puede ser el material equivocado para enseñar un modelo de artículos.",
  rightsTitle: "¿Podemos usarlo?",
  rightsHelp: "Confirmar que la licencia exacta permite entrenar localmente y usar el resultado como planeamos.",
  contentTitle: "¿Contiene palabras del artículo?",
  contentHelp: "Nuestro clasificador necesita el mismo tipo de titular o texto que recibirá después del lanzamiento.",
  labelsTitle: "¿Qué significan sus etiquetas?",
  labelsHelp: "Evento de inundación, alerta, lluvia intensa y noticia irrelevante son respuestas distintas, no nombres intercambiables.",
  separationTitle: "¿Podemos mantener una prueba honesta?",
  separationHelp: "Los ejemplos importados conservan su fuente y los artículos nuevos de CrisisPulse quedan intactos para la prueba final.",
  summaryEyebrow: "Decisión actual",
  summaryHeading: "Hay datos externos útiles, pero ninguno sustituye directamente sus etiquetas.",
  sourceCount: "Fuentes comprobadas",
  trainingApproved: "Aprobadas para entrenamiento directo",
  supportOnly: "Solo apoyo o investigación",
  blocked: "Bloqueadas para entrenamiento",
  largeDownloads: "Archivos grandes descargados",
  zeroDownloads: "0",
  zeroDownloadsHelp: "Solo se inspeccionaron descripciones públicas y pequeños registros de metadatos.",
  sourceCountHelp: "Cada fuente conserva su propia evidencia y decisión.",
  trainingApprovedHelp: "Requiere derechos aprobados, texto compatible y etiquetas compatibles.",
  supportOnlyHelp: "Puede validar eventos o apoyar investigación sin convertirse en una fila del clasificador.",
  blockedHelp: "Los derechos desconocidos o material incompatible quedan fuera del modelo.",
  candidates: "Conjuntos candidatos",
  candidatesHeading: "Vea exactamente por qué cada fuente puede —o no puede— entrenar el clasificador.",
  candidatesDescription: "Ninguna etiqueta externa se convierte silenciosamente en una respuesta de CrisisPulse. Desconocido significa bloqueado hasta resolverlo.",
  license: "Derechos",
  articleText: "Texto del artículo",
  labelFit: "Compatibilidad de etiqueta",
  access: "Acceso",
  finalUse: "Decisión de CrisisPulse",
  trainingDecision: "Entrenamiento",
  importDecision: "Importación",
  approved: "Aprobado",
  blockedStatus: "Bloqueado",
  directFit: "Compatibilidad directa",
  partialFit: "Compatibilidad parcial",
  incompatible: "No compatible",
  unknown: "Desconocido",
  available: "Disponible",
  unavailable: "No incluido",
  openSource: "Abrir fuente oficial",
  labelCrosswalk: "Correspondencia de etiquetas",
  sourceLabel: "Etiqueta de origen",
  crisisPulseLabel: "Etiqueta de CrisisPulse",
  use: "Cómo puede usarse",
  noDirectMapping: "No hay una correspondencia directa segura documentada",
  evidence: "Evidencia comprobada",
  notes: "Notas importantes",
  loadingHeading: "Comprobando el registro de datos externos…",
  loadingHelp: "No se descargan archivos grandes y no se inicia ningún entrenamiento.",
  errorHeading: "No se pudo cargar la auditoría de datos.",
  errorHelp: "Asegúrese de que la API local de CrisisPulse esté activa y vuelva a intentar. No se cambió ningún dato o modelo.",
  retry: "Intentar de nuevo",
  emptyHeading: "Todavía no hay conjuntos externos registrados.",
  emptyHelp: "El registro está vacío; los datos externos permanecen bloqueados por defecto.",
  nextEyebrow: "Qué sucede después",
  nextHeading: "Construir el motor ahora; admitir datos solo después de aprobar.",
  nextDescription: "Así avanzamos sin producir un modelo que parezca impresionante pero haya aprendido la lección equivocada.",
  nextOne: "Mantener sus revisiones como el núcleo confiable de cuatro clases",
  nextOneHelp: "Sus etiquetas enseñan exactamente las distinciones que CrisisPulse debe hacer.",
  nextTwo: "Usar etiquetas externas compatibles con procedencia permanente",
  nextTwoHelp: "Cada fila importada registra su fuente, etiqueta original, licencia y regla de conversión.",
  nextThree: "Ejecutar un modelo base en CPU antes de la RTX 4070",
  nextThreeHelp: "Una prueba rápida demuestra que los datos y la separación funcionan antes de un experimento local mayor.",
  nextFour: "Proteger una reserva nativa más reciente",
  nextFourHelp: "La prueba final usa artículos que el modelo nunca vio, separados por tiempo, editor e historia.",
  policyTitle: "Valor predeterminado seguro",
  policyHelp: "Licencia desconocida = bloqueada. Las etiquetas externas no se tratan como verdad humana de CrisisPulse. Siempre se requiere una reserva nativa.",
  readOnly: "Auditoría de solo lectura",
  readOnlyHelp: "Esta pantalla no puede descargar conjuntos, iniciar entrenamiento, desplegar un modelo ni cambiar revisiones.",
  footerHome: "Administración de CrisisPulse",
});

type LabelMapping = {
  source_label: string;
  crisispulse_label: string;
  use: string;
};

type AuditEvidence = {
  url: string;
  supports: string;
};

type ExternalDataset = {
  id: string;
  source_name: string;
  source_url: string;
  doi: string;
  access_state: string;
  license_state: string;
  license_training_approved: boolean;
  article_text_availability: string;
  label_type: string;
  compatibility_status: string;
  compatibility_mapping: LabelMapping[];
  import_decision: string;
  training_decision: string;
  evidence: AuditEvidence[];
  notes: string[];
  last_checked: string;
};

type ExternalDatasetAudit = {
  schema_version: number;
  last_checked: string;
  policy: {
    unknown_license_action: string;
    external_labels_are_ground_truth: boolean;
    native_holdout_required: boolean;
    notes: string[];
  };
  datasets: ExternalDataset[];
};

type RequestState = "loading" | "refreshing" | "ready" | "stale" | "error";
type MessageKey = keyof typeof messages.en;

const auditURL = "/api/v1/training/external-datasets";

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === "object" && value !== null
);

const accessStates = new Set(["public_download", "public_project_page", "paper_only_dataset_access_not_verified", "publication_only_dataset_access_not_verified"]);
const licenseStates = new Set(["unknown", "verified_permissive", "verified_restricted", "incompatible"]);
const textStates = new Set(["available", "not_verified", "not_available", "social_posts_only"]);
const compatibilityStates = new Set(["direct", "partial", "low", "incompatible"]);
const trainingDecisions = new Set(["approved", "blocked", "not_recommended"]);

const isStringArray = (value: unknown): value is string[] => (
  Array.isArray(value) && value.every((item) => typeof item === "string")
);

const isLabelMapping = (value: unknown): value is LabelMapping => (
  isRecord(value)
  && typeof value.source_label === "string"
  && typeof value.crisispulse_label === "string"
  && typeof value.use === "string"
);

const isAuditEvidence = (value: unknown): value is AuditEvidence => (
  isRecord(value)
  && typeof value.url === "string"
  && typeof value.supports === "string"
);

const isExternalDataset = (value: unknown): value is ExternalDataset => (
  isRecord(value)
  && typeof value.id === "string"
  && typeof value.source_name === "string"
  && typeof value.source_url === "string"
  && typeof value.doi === "string"
  && typeof value.access_state === "string"
  && accessStates.has(value.access_state)
  && typeof value.license_state === "string"
  && licenseStates.has(value.license_state)
  && typeof value.license_training_approved === "boolean"
  && typeof value.article_text_availability === "string"
  && textStates.has(value.article_text_availability)
  && typeof value.label_type === "string"
  && typeof value.compatibility_status === "string"
  && compatibilityStates.has(value.compatibility_status)
  && Array.isArray(value.compatibility_mapping)
  && value.compatibility_mapping.every(isLabelMapping)
  && typeof value.import_decision === "string"
  && typeof value.training_decision === "string"
  && trainingDecisions.has(value.training_decision)
  && Array.isArray(value.evidence)
  && value.evidence.every(isAuditEvidence)
  && isStringArray(value.notes)
  && typeof value.last_checked === "string"
);

const isExternalDatasetAudit = (value: unknown): value is ExternalDatasetAudit => (
  isRecord(value)
  && value.schema_version === 1
  && typeof value.last_checked === "string"
  && isRecord(value.policy)
  && value.policy.unknown_license_action === "block_training"
  && value.policy.external_labels_are_ground_truth === false
  && value.policy.native_holdout_required === true
  && isStringArray(value.policy.notes)
  && Array.isArray(value.datasets)
  && value.datasets.every(isExternalDataset)
);

const safeExternalURL = (value: string) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
};

const humanize = (value: string) => value
  .replaceAll("_", " ")
  .replace(/\b\w/g, (character) => character.toUpperCase());

const spanishAuditProse: Record<string, string> = {
  "The public record describes one 667.1 MB Parquet file containing 2.6 million structured historical flood-event records.": "El registro público describe un archivo Parquet de 667.1 MB con 2.6 millones de observaciones históricas estructuradas de inundaciones.",
  "The official DOI metadata identifies the dataset license as Creative Commons Attribution 4.0 International.": "Los metadatos oficiales del DOI identifican la licencia como Creative Commons Attribution 4.0 Internacional.",
  "The primary manuscript documents only uuid, area_km2, start_date, end_date, and geometry in the released schema.": "El manuscrito principal documenta únicamente uuid, area_km2, start_date, end_date y geometry en el esquema publicado.",
  "The project distinguishes reported flood events from warnings, policy discussion, and general risk.": "El proyecto distingue inundaciones reportadas de alertas, discusiones de políticas y riesgo general.",
  "The CC BY 4.0 license permits reuse with attribution, but the file contains no article text, URL, title, publisher, or class-label column.": "La licencia CC BY 4.0 permite reutilización con atribución, pero el archivo no contiene texto, URL, título, editor ni columna de clase del artículo.",
  "This is an event archive, not a four-class article-text dataset.": "Es un archivo de eventos, no un conjunto de texto de artículos con cuatro clases.",
  "It may validate time-and-location matches for reported-flooding positives, but it cannot directly train the CrisisPulse article classifier.": "Puede validar coincidencias de tiempo y lugar para inundaciones reportadas, pero no puede entrenar directamente el clasificador de artículos.",
  "The paper reports a Bangladesh news corpus and an expert-annotated binary flood-versus-not-flood subset.": "El artículo informa de un corpus de noticias de Bangladés y un subconjunto binario inundación/no inundación anotado por expertos.",
  "This is the closest located dataset to the CrisisPulse article-classification task.": "Es el conjunto localizado más cercano a la tarea de clasificación de artículos de CrisisPulse.",
  "Its not-flood class can mix flood warnings, heavy rain, policy discussion, and unrelated material.": "Su clase no inundación puede mezclar alertas, lluvia intensa, políticas y material no relacionado.",
  "A usable data file, article-text rights, and a training license have not yet been verified.": "Todavía no se han verificado un archivo utilizable, los derechos del texto ni una licencia de entrenamiento.",
  "The paper describes human-labeled social-media posts across disaster events and humanitarian categories.": "El artículo describe publicaciones sociales etiquetadas por personas en desastres y categorías humanitarias.",
  "The project page is the dataset access reference supplied by the authors.": "La página del proyecto es la referencia de acceso proporcionada por los autores.",
  "The official terms limit use to humanitarian-computing research and impose confidentiality and deletion requirements.": "Los términos oficiales limitan el uso a investigación humanitaria e imponen confidencialidad y eliminación.",
  "Social-media wording and humanitarian categories do not directly match news headlines or the four CrisisPulse classes.": "El lenguaje social y las categorías humanitarias no coinciden directamente con titulares ni con las cuatro clases de CrisisPulse.",
  "The current terms are not suitable for commercial CrisisPulse product training.": "Los términos actuales no son adecuados para entrenar un producto comercial de CrisisPulse.",
  "A separately approved research experiment would still need to preserve the original social-media provenance.": "Un experimento de investigación aprobado por separado aún tendría que conservar la procedencia social original.",
  "The project describes a labeled multimodal social-media crisis dataset.": "El proyecto describe un conjunto multimodal etiquetado de crisis en redes sociales.",
  "The medium, event coverage, and labels do not directly match the CrisisPulse article classifier.": "El medio, la cobertura y las etiquetas no coinciden directamente con el clasificador de artículos.",
  "Image and social-post experiments are outside the current training milestone.": "Los experimentos con imágenes y publicaciones sociales quedan fuera del hito actual.",
  "The primary publication describes human annotation of agency news into flood and other concrete-event classes.": "La publicación principal describe anotación humana de noticias de agencia en inundaciones y otros eventos concretos.",
  "The news medium and flood-event class are conceptually close to CrisisPulse.": "El medio noticioso y la clase de inundación son conceptualmente cercanos a CrisisPulse.",
  "No public corpus download or reusable dataset license was verified from the primary publication.": "No se verificó una descarga pública del corpus ni una licencia reutilizable en la publicación principal.",
  "The non-flood classes still do not map cleanly to flood warning, heavy rain, and unrelated news.": "Las clases distintas de inundación no se corresponden claramente con alerta, lluvia intensa y noticias no relacionadas.",
  "The NIST publication describes annotated social-media posts for crisis events, information types, and priority.": "La publicación de NIST describe publicaciones sociales anotadas por evento, tipo de información y prioridad.",
  "These annotations may inform a future urgency model but do not supply the current flood article labels.": "Estas anotaciones pueden ayudar a un futuro modelo de urgencia, pero no aportan las etiquetas actuales de artículos.",
  "Dataset access terms and any underlying platform-content restrictions must be reviewed separately.": "Los términos de acceso y las restricciones de contenido de la plataforma deben revisarse por separado.",
};

const decisionTone = (dataset: ExternalDataset) => {
  if (dataset.training_decision === "approved" && dataset.license_training_approved) return "approved";
  if (dataset.training_decision === "not_recommended" && dataset.license_state !== "unknown") return "support";
  return "blocked";
};

export default function DatasetAuditPage() {
  const { locale, localeTag } = useLocale();
  const pageMessages = messages[locale];
  const t = useCallback((key: MessageKey, values: Record<string, string | number> = {}) => (
    formatMessage(pageMessages[key], values)
  ), [pageMessages]);
  const [audit, setAudit] = useState<ExternalDatasetAudit | null>(null);
  const [requestState, setRequestState] = useState<RequestState>("loading");
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);

  useEffect(() => {
    document.title = pageMessages.documentTitle;
    let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) {
      description = document.createElement("meta");
      description.name = "description";
      document.head.appendChild(description);
    }
    description.content = pageMessages.documentDescription;
  }, [pageMessages.documentDescription, pageMessages.documentTitle]);

  const loadAudit = useCallback(async (parentSignal?: AbortSignal) => {
    setRequestState((current) => current === "ready" || current === "stale" ? "refreshing" : "loading");
    const controller = new AbortController();
    const abortFromParent = () => controller.abort();
    if (parentSignal?.aborted) controller.abort();
    else parentSignal?.addEventListener("abort", abortFromParent, { once: true });
    const timeout = window.setTimeout(() => controller.abort(), 8_000);
    try {
      const response = await fetch(auditURL, {
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("external dataset audit request failed");
      const payload: unknown = await response.json();
      if (!isExternalDatasetAudit(payload)) throw new Error("unexpected external dataset audit response");
      setAudit(payload);
      setLastLoadedAt(new Date());
      setRequestState("ready");
    } catch {
      if (controller.signal.aborted && parentSignal?.aborted) return;
      setRequestState((current) => current === "refreshing" ? "stale" : "error");
    } finally {
      window.clearTimeout(timeout);
      parentSignal?.removeEventListener("abort", abortFromParent);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const initialLoad = window.setTimeout(() => void loadAudit(controller.signal), 0);
    return () => {
      window.clearTimeout(initialLoad);
      controller.abort();
    };
  }, [loadAudit]);

  const formatEastern = useCallback((value: string | Date) => {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString(localeTag, {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  }, [localeTag]);

  const formatAuditDate = useCallback((value: string) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return "—";
    const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
    return date.toLocaleDateString(localeTag, {
      timeZone: "UTC",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }, [localeTag]);

  const statusLabel = useCallback((value: string) => {
    const labels: Record<string, { en: string; es: string }> = {
      approved: { en: "Approved", es: "Aprobado" },
      verified_permissive: { en: "Verified permissive", es: "Permisiva verificada" },
      verified_restricted: { en: "Restricted", es: "Restringida" },
      unknown: { en: "Unknown", es: "Desconocido" },
      absent: { en: "Not included", es: "No incluido" },
      unavailable: { en: "Not included", es: "No incluido" },
      not_available: { en: "Not included", es: "No incluido" },
      not_verified: { en: "Not verified", es: "No verificado" },
      social_posts_only: { en: "Social posts only", es: "Solo publicaciones sociales" },
      available: { en: "Available", es: "Disponible" },
      partial: { en: "Partial", es: "Parcial" },
      low: { en: "Low fit", es: "Baja compatibilidad" },
      direct: { en: "Direct fit", es: "Compatibilidad directa" },
      partial_mapping: { en: "Partial fit", es: "Compatibilidad parcial" },
      incompatible: { en: "Not compatible", es: "No compatible" },
      public_download: { en: "Public download", es: "Descarga pública" },
      public_project_page: { en: "Public project page", es: "Página pública del proyecto" },
      paper_only: { en: "Paper only", es: "Solo el artículo" },
      paper_only_dataset_access_not_verified: { en: "Paper only; dataset unverified", es: "Solo artículo; conjunto no verificado" },
      publication_only_dataset_access_not_verified: { en: "Publication only; dataset unverified", es: "Solo publicación; conjunto no verificado" },
      request_required: { en: "Request required", es: "Solicitud necesaria" },
      blocked: { en: "Blocked", es: "Bloqueado" },
      support_only: { en: "Support only", es: "Solo apoyo" },
      event_validation_only: { en: "Event validation only", es: "Solo validación de eventos" },
      approved_for_event_validation_only: { en: "Approved for event validation only", es: "Aprobado solo para validar eventos" },
      blocked_pending_dataset_access_license_and_text_review: { en: "Blocked pending files and rights", es: "Bloqueado hasta verificar archivos y derechos" },
      blocked_by_research_only_terms: { en: "Blocked by research-only terms", es: "Bloqueado por términos solo de investigación" },
      do_not_import_for_article_classifier_yet: { en: "Do not import for this classifier", es: "No importar para este clasificador" },
      blocked_pending_license_and_schema_review: { en: "Blocked pending rights and schema", es: "Bloqueado hasta verificar derechos y esquema" },
      not_recommended: { en: "Not recommended", es: "No recomendado" },
      approved_for_training: { en: "Approved for training", es: "Aprobado para entrenamiento" },
      reported_flooding: { en: "Flooding reported", es: "Inundación reportada" },
      flood_risk_warning: { en: "Flood risk / warning", es: "Riesgo o alerta de inundación" },
      heavy_rain_only: { en: "Heavy rain only", es: "Solo lluvia intensa" },
      not_flood_related: { en: "Not flood-related", es: "No relacionado con inundaciones" },
      no_direct_mapping: { en: "No direct mapping", es: "Sin correspondencia directa" },
      weak_supervision_or_event_validation: { en: "Weak supervision or event validation", es: "Supervisión débil o validación de eventos" },
      candidate_supervised_label_after_manual_mapping_audit: { en: "Candidate label after a manual mapping audit", es: "Etiqueta candidata después de una auditoría manual" },
      must_not_be_collapsed_into_one_crisispulse_class: { en: "Must be manually separated", es: "Debe separarse manualmente" },
      optional_auxiliary_crisis_language_research: { en: "Optional crisis-language research only", es: "Solo investigación opcional de lenguaje de crisis" },
      optional_auxiliary_multimodal_research: { en: "Optional multimodal research only", es: "Solo investigación multimodal opcional" },
      candidate_supervised_label_after_access_and_mapping_audit: { en: "Candidate after access and mapping audit", es: "Candidata después de auditar acceso y correspondencia" },
      requires_manual_relabeling_for_warning_rain_and_unrelated_classes: { en: "Requires manual relabeling", es: "Requiere reetiquetado manual" },
      possible_future_severity_or_urgency_research: { en: "Possible future urgency research", es: "Posible investigación futura de urgencia" },
      "news-derived structured flood-event records": { en: "Structured flood-event records derived from news", es: "Registros estructurados de inundaciones derivados de noticias" },
      "expert binary article classification": { en: "Expert binary article labels", es: "Etiquetas binarias de artículos por expertos" },
      "humanitarian-category labels on social-media posts": { en: "Humanitarian labels on social posts", es: "Etiquetas humanitarias en publicaciones sociales" },
      "multimodal crisis labels on social-media posts and images": { en: "Crisis labels on social posts and images", es: "Etiquetas de crisis en publicaciones e imágenes" },
      "human-annotated agency-news event classes": { en: "Human event labels on agency news", es: "Etiquetas humanas de eventos en noticias de agencia" },
      "crisis information-type and priority annotations on social-media posts": { en: "Crisis type and priority labels on social posts", es: "Etiquetas de tipo y prioridad en publicaciones sociales" },
      "reported past or ongoing flood event": { en: "Reported past or ongoing flood event", es: "Inundación pasada o actual reportada" },
      flood: { en: "Flood", es: "Inundación" },
      "not flood": { en: "Not flood", es: "No inundación" },
      "humanitarian information categories": { en: "Humanitarian information categories", es: "Categorías de información humanitaria" },
      "crisis informativeness and humanitarian categories": { en: "Crisis and humanitarian categories", es: "Categorías de crisis y ayuda humanitaria" },
      "storms or none": { en: "Storms or none", es: "Tormentas o ninguna" },
      "incident information types and priority": { en: "Incident types and priority", es: "Tipos y prioridad del incidente" },
    };
    return labels[value]?.[locale] ?? humanize(value);
  }, [locale]);

  const auditProse = useCallback((value: string) => (
    locale === "es" ? spanishAuditProse[value] ?? value : value
  ), [locale]);

  const summary = useMemo(() => {
    const datasets = audit?.datasets ?? [];
    const approved = datasets.filter((dataset) => decisionTone(dataset) === "approved").length;
    const support = datasets.filter((dataset) => decisionTone(dataset) === "support").length;
    return { total: datasets.length, approved, support, blocked: datasets.length - approved - support };
  }, [audit?.datasets]);

  const checkSteps = [
    ["01", "rightsTitle", "rightsHelp"],
    ["02", "contentTitle", "contentHelp"],
    ["03", "labelsTitle", "labelsHelp"],
    ["04", "separationTitle", "separationHelp"],
  ] as const;

  return (
    <main className="dataset-audit-page">
      <header className="site-header">
        <Link className="brand" href="/" aria-label={t("brandHome")}>
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>CrisisPulse</span>
        </Link>
        <nav className="header-nav" aria-label={t("primaryNavigation")}>
          <Link href="/">{t("dashboard")}</Link>
          <Link href="/admin">{t("admin")}</Link>
          <Link href="/admin/training-data">{t("trainingData")}</Link>
          <Link aria-current="page" className="active" href="/admin/training-data/dataset-audit">{t("audit")}</Link>
        </nav>
        <div className="header-meta" aria-live="polite">
          <span aria-hidden="true" className={requestState === "ready" || requestState === "refreshing" ? "live-dot" : "live-dot snapshot"} />
          <strong>{requestState === "loading"
            ? t("checkingAudit")
            : requestState === "error"
              ? t("auditUnavailable")
              : requestState === "stale"
                ? t("staleAudit")
                : t("registerLoaded")}</strong>
        </div>
        <LanguageSwitcher />
      </header>

      <section className="eda-hero" aria-labelledby="audit-heading">
        <div>
          <p className="eyebrow">{t("eyebrow")}</p>
          <h1 id="audit-heading">{t("heroTitle")}</h1>
          <p>{t("heroDescription")}</p>
          <div className="eda-hero-actions">
            <Link href="/admin/training-data">{t("backToTraining")}</Link>
            <button disabled={requestState === "loading" || requestState === "refreshing"} onClick={() => void loadAudit()} type="button">
              {requestState === "refreshing" ? t("refreshing") : t("refresh")}
            </button>
          </div>
          {lastLoadedAt ? <small>{t("registerLoadedAt", { time: formatEastern(lastLoadedAt) })}</small> : null}
        </div>
        <aside>
          <strong aria-hidden="true">4</strong>
          <span>{t("fourChecks")}</span>
          <p>{t("readOnlyHelp")}</p>
        </aside>
      </section>

      {requestState === "stale" ? <div className="eda-stale-notice" role="status">{t("refreshFailed")}</div> : null}

      <section className="eda-section eda-explainer" aria-labelledby="four-checks-heading">
        <div className="eda-section-heading">
          <p className="eyebrow">{t("fourChecks")}</p>
          <h2 id="four-checks-heading">{t("fourChecksHeading")}</h2>
          <p>{t("fourChecksDescription")}</p>
        </div>
        <ol>
          {checkSteps.map(([number, titleKey, helpKey]) => (
            <li key={number}>
              <span>{number}</span>
              <h3>{t(titleKey)}</h3>
              <p>{t(helpKey)}</p>
            </li>
          ))}
        </ol>
      </section>

      {requestState === "loading" ? (
        <section className="eda-state" aria-busy="true" aria-live="polite">
          <span className="eda-spinner" aria-hidden="true" />
          <div><h2>{t("loadingHeading")}</h2><p>{t("loadingHelp")}</p></div>
        </section>
      ) : requestState === "error" ? (
        <section className="eda-state error" role="alert">
          <span aria-hidden="true">!</span>
          <div><h2>{t("errorHeading")}</h2><p>{t("errorHelp")}</p><button onClick={() => void loadAudit()} type="button">{t("retry")}</button></div>
        </section>
      ) : audit ? (
        <>
          <section className="eda-section" aria-labelledby="audit-summary-heading">
            <div className="eda-section-heading">
              <p className="eyebrow">{t("summaryEyebrow")}</p>
              <h2 id="audit-summary-heading">{t("summaryHeading")}</h2>
            </div>
            <div className="eda-summary-grid">
              <article><span>{t("sourceCount")}</span><strong>{summary.total.toLocaleString(localeTag)}</strong><p>{t("sourceCountHelp")}</p></article>
              <article className="approved"><span>{t("trainingApproved")}</span><strong>{summary.approved.toLocaleString(localeTag)}</strong><p>{t("trainingApprovedHelp")}</p></article>
              <article className="support"><span>{t("supportOnly")}</span><strong>{summary.support.toLocaleString(localeTag)}</strong><p>{t("supportOnlyHelp")}</p></article>
              <article className="blocked"><span>{t("blocked")}</span><strong>{summary.blocked.toLocaleString(localeTag)}</strong><p>{t("blockedHelp")}</p></article>
              <article className="downloads"><span>{t("largeDownloads")}</span><strong>{t("zeroDownloads")}</strong><p>{t("zeroDownloadsHelp")}</p></article>
            </div>
          </section>

          <section className="eda-section eda-candidates" aria-labelledby="candidate-heading">
            <div className="eda-section-heading">
              <p className="eyebrow">{t("candidates")}</p>
              <h2 id="candidate-heading">{t("candidatesHeading")}</h2>
              <p>{t("candidatesDescription")}</p>
            </div>
            {audit.datasets.length === 0 ? (
              <div className="eda-empty"><h3>{t("emptyHeading")}</h3><p>{t("emptyHelp")}</p></div>
            ) : (
              <div className="eda-dataset-list">
                {audit.datasets.map((dataset, index) => {
                  const tone = decisionTone(dataset);
                  const sourceURL = safeExternalURL(dataset.source_url);
                  const articleTextPresent = dataset.article_text_availability === "available";
                  return (
                    <article className={`eda-dataset ${tone}`} key={dataset.id}>
                      <header>
                        <div>
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          <h3>{dataset.source_name}</h3>
                          {dataset.doi ? <small>DOI {dataset.doi}</small> : null}
                        </div>
                        <b>{statusLabel(dataset.training_decision)}</b>
                      </header>
                      <div className="eda-audit-strip">
                        <div className={dataset.license_training_approved ? "pass" : "block"}>
                          <span>{t("license")}</span>
                          <strong>{statusLabel(dataset.license_state)}</strong>
                        </div>
                        <div className={articleTextPresent ? "pass" : "block"}>
                          <span>{t("articleText")}</span>
                          <strong>{statusLabel(dataset.article_text_availability)}</strong>
                        </div>
                        <div className={dataset.compatibility_status === "direct" ? "pass" : dataset.compatibility_status === "partial" ? "warn" : "block"}>
                          <span>{t("labelFit")}</span>
                          <strong>{statusLabel(dataset.compatibility_status)}</strong>
                        </div>
                        <div>
                          <span>{t("access")}</span>
                          <strong>{statusLabel(dataset.access_state)}</strong>
                        </div>
                      </div>
                      <dl className="eda-decisions">
                        <div><dt>{t("trainingDecision")}</dt><dd>{statusLabel(dataset.training_decision)}</dd></div>
                        <div><dt>{t("importDecision")}</dt><dd>{statusLabel(dataset.import_decision)}</dd></div>
                        <div><dt>{t("labelFit")}</dt><dd>{statusLabel(dataset.label_type)}</dd></div>
                      </dl>
                      <div className="eda-detail-grid">
                        <section>
                          <h4>{t("labelCrosswalk")}</h4>
                          {dataset.compatibility_mapping.length ? (
                            <div className="eda-crosswalk">
                              {dataset.compatibility_mapping.map((mapping, mappingIndex) => (
                                <div key={`${mapping.source_label}-${mappingIndex}`}>
                                  <span><small>{t("sourceLabel")}</small>{statusLabel(mapping.source_label)}</span>
                                  <i aria-hidden="true">→</i>
                                  <span><small>{t("crisisPulseLabel")}</small>{mapping.crisispulse_label ? statusLabel(mapping.crisispulse_label) : "—"}</span>
                                  <p><small>{t("use")}</small>{statusLabel(mapping.use)}</p>
                                </div>
                              ))}
                            </div>
                          ) : <p>{t("noDirectMapping")}</p>}
                        </section>
                        <section>
                          <h4>{t("notes")}</h4>
                          <ul>{dataset.notes.map((note) => <li key={note}>{auditProse(note)}</li>)}</ul>
                        </section>
                        <section className="eda-evidence">
                          <h4>{t("evidence")}</h4>
                          <ul>
                            {dataset.evidence.map((item) => {
                              const evidenceURL = safeExternalURL(item.url);
                              return (
                                <li key={`${item.url}-${item.supports}`}>
                                  {evidenceURL ? <a href={evidenceURL} rel="noreferrer" target="_blank">{auditProse(item.supports)} <span aria-hidden="true">↗</span></a> : auditProse(item.supports)}
                                </li>
                              );
                            })}
                          </ul>
                        </section>
                      </div>
                      <footer>
                        <span>{t("evidenceReviewed", { date: formatAuditDate(dataset.last_checked) })}</span>
                        {sourceURL ? <a href={sourceURL} rel="noreferrer" target="_blank">{t("openSource")} <span aria-hidden="true">↗</span></a> : null}
                      </footer>
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          <section className="eda-next" aria-labelledby="next-heading">
            <div>
              <p className="eyebrow">{t("nextEyebrow")}</p>
              <h2 id="next-heading">{t("nextHeading")}</h2>
              <p>{t("nextDescription")}</p>
            </div>
            <ol>
              {[["01", "nextOne", "nextOneHelp"], ["02", "nextTwo", "nextTwoHelp"], ["03", "nextThree", "nextThreeHelp"], ["04", "nextFour", "nextFourHelp"]].map(([number, heading, help]) => (
                <li key={number}><span>{number}</span><div><strong>{t(heading as MessageKey)}</strong><p>{t(help as MessageKey)}</p></div></li>
              ))}
            </ol>
          </section>

          <aside className="eda-policy">
            <span aria-hidden="true">✓</span>
            <div><strong>{t("policyTitle")}</strong><p>{t("policyHelp")}</p></div>
          </aside>
        </>
      ) : null}

      <footer className="eda-footer">
        <div><strong>{t("readOnly")}</strong><p>{t("readOnlyHelp")}</p></div>
        <Link href="/admin">{t("footerHome")}</Link>
      </footer>
    </main>
  );
}
