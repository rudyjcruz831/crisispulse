"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import bundledDashboardData from "../data/dashboard.json";
import { defineMessages, formatMessage, LanguageSwitcher, useLocale } from "./i18n";

type EvidenceSource = { domain: string; url: string };
type EvidenceStory = {
  story_id: string;
  seen_at: string;
  location: string | null;
  themes: string[];
  sources: EvidenceSource[];
  title?: string | null;
};
type PendingForecast = {
  region_code: string;
  window_start: string;
  matures_at: string;
  hours_remaining: number;
  stories_at_detection: number;
  domains_at_detection: number;
};
type ForecastModelMetrics = {
  average_precision: number | null;
  brier_score: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  predicted_alerts: number;
  false_alerts_per_day: number | null;
};
type PendingModelPrediction = {
  region_code: string;
  window_start: string;
  model_score: number;
  clears_alert_threshold: boolean;
};
type ForecastModel = {
  status: "ready" | "unavailable";
  type: string;
  decision_threshold: number | null;
  scores_are_calibrated_probabilities: boolean;
  training_rows: number;
  validation_rows: number;
  test_rows: number;
  test_positives: number;
  validation_hours: number;
  test_hours: number;
  validation_metrics: Partial<ForecastModelMetrics>;
  test_metrics: Partial<ForecastModelMetrics>;
  test_window: { prediction_start?: string; prediction_end?: string };
  pending_predictions: PendingModelPrediction[];
  guardrails: string[];
};
type ForecastSummary = {
  target: {
    name: string;
    horizon_hours: number;
    domain_threshold: number;
    definition: string;
  };
  eligible_windows: number;
  positive_outcomes: number;
  evaluation_ready_windows: number;
  candidate_predictions: number;
  evaluated_predictions: number;
  pending_predictions: PendingForecast[];
  precision: number | null;
  recall: number | null;
  model: ForecastModel;
};
type BundledSignal = (typeof bundledDashboardData)["signals"][number];
type Signal = Omit<BundledSignal, "evidence"> & { evidence: EvidenceStory[] };
type DashboardData = Omit<typeof bundledDashboardData, "signals" | "forecast"> & {
  signals: Signal[];
  forecast: ForecastSummary;
  latest_coverage?: EvidenceStory[];
};
type ReviewDecision = "confirmed_event" | "irrelevant_news" | "uncertain";
type ReviewRecord = {
  signal_id: string;
  region_code: string;
  window_start: string;
  decision: ReviewDecision;
  reviewed_at: string;
};
type ReviewsResponse = { reviews: ReviewRecord[] };
type ReviewResponse = { review: ReviewRecord };
type ReviewSummary = {
  total_reviews: number;
  confirmed_events: number;
  irrelevant_news: number;
  uncertain: number;
  resolved_reviews: number;
  minimum_sample: number;
  remaining_to_sample: number;
  confirmed_event_rate: number | null;
  irrelevant_news_rate: number | null;
  status: "collecting_labels" | "sample_ready";
};

const snapshotURL = "/api/v1/snapshot";
const reviewsURL = "/api/v1/reviews";
const reviewSummaryURL = "/api/v1/reviews/summary";
const reviewExportURL = "/api/v1/reviews/export.csv";

const messages = defineMessages(
  {
    documentTitle: "CrisisPulse — Flood reporting signals",
    documentDescription: "Explainable flood-reporting anomaly detection using GDELT news data.",
    dashboardHome: "CrisisPulse dashboard home",
    primaryNavigation: "Primary navigation",
    dashboard: "Dashboard",
    admin: "Admin",
    liveConnected: "Live API connected",
    verifiedSnapshot: "Verified local snapshot",
    dashboardSections: "Dashboard sections",
    overview: "Overview",
    coverage: "Coverage",
    review: "Review",
    forecast: "Forecast",
    signals: "Signals",
    globalMonitor: "Global flood reporting monitor",
    candidateHeadlineOne: "{count} unusual reporting signal needs review.",
    candidateHeadlineMany: "{count} unusual reporting signals need review.",
    noUnusualSignals: "No unusual reporting signals right now.",
    reviewedWindow: "CrisisPulse reviewed {window} of GDELT news activity.",
    windowRange: "{start}–{end}",
    candidateLede: " These candidates passed the history and source-diversity gates and now need evidence review.",
    cleanLede: " The latest eligible scoring hour opened cleanly, with no candidate alerts.",
    reviewRequired: "Evidence review required.",
    behavingAsDesigned: "System behaving as designed.",
    candidateGuardrail: "A candidate is an unusual news pattern, not proof of a physical disaster.",
    historyGuardrail: "The history gate did not turn ordinary coverage into an alert.",
    currentWatchStatus: "Current watch status",
    currentWatch: "Current watch",
    candidateAnomalies: "Candidate anomalies",
    minimumHistory: "Minimum history",
    hours: "{count} hours",
    minimumEvidence: "Minimum evidence",
    storiesDomains: "{stories} stories · {domains} domains",
    alertThreshold: "Alert threshold",
    thresholdDefinition: "z ≥ {threshold} or a gated zero-baseline jump",
    dataCoverage: "Data coverage",
    retainedArticles: "Flood articles retained",
    duplicateRemoval: "After exact duplicate removal",
    regionsObserved: "Regions observed",
    regionTypes: "Named and unresolved regions",
    hourlyWindows: "Hourly windows",
    hourlyStoryGroups: "Hourly story groups",
    groupsDefinition: "Distinct within each region and hour",
    publisherEvidence: "Publisher evidence",
    latestCoverage: "Latest flood coverage",
    latestCoverageDescription: "Recent publisher reports that passed CrisisPulse's flood-topic checks. These links are evidence, not automatic confirmation of a physical incident.",
    recentGroupsAria: "{count} recent story groups",
    recentGroupOne: "recent story group",
    recentGroupMany: "recent story groups",
    multiSourceCoverage: "Multi-source coverage",
    corroboratedCoverage: "Corroborated coverage",
    singlePublisher: "Single publisher",
    locationUnresolved: "Location unresolved",
    independentPublishers: "{count} independent publishers",
    readPublisherReport: "Read publisher report",
    noRecentCoverage: "No recent eligible coverage in this window.",
    coverageWillFill: "The feed will fill automatically when the next checked flood reports arrive.",
    humanValidation: "Human validation",
    reviewQueue: "Review queue",
    reviewQueueDescription: "Label unusual reporting so CrisisPulse can separate credible events from irrelevant coverage and ambiguous evidence.",
    labeledProgress: "{reviewed} of {total} labeled",
    realEvent: "Real event",
    irrelevantNews: "Irrelevant news",
    irrelevant: "Irrelevant",
    uncertain: "Uncertain",
    savedReview: "Saved “{decision}” for {region}.",
    saveReviewFailed: "The decision could not be saved. Check that the local API is running.",
    needsReview: "Needs review",
    storyGroups: "Story groups",
    sourceDomains: "Source domains",
    priorBaseline: "Prior baseline",
    robustScore: "Robust score",
    sourceEvidenceFor: "Source evidence for {region}",
    directEvidence: "Direct publisher evidence",
    sourceLinksByStory: "Source links by distinct story",
    groupOne: "group",
    groupMany: "groups",
    evidenceNote: "GDELT tags are a starting point, not proof. Clear conflicts with a URL-derived headline are downgraded and cannot create an alert.",
    storyNumber: "Story {number}",
    publisherLinkOne: "{count} publisher link",
    publisherLinkMany: "{count} publisher links",
    noSafeLink: "No safe publisher link retained",
    gdeltTag: "GDELT tag: {theme}",
    compareVersions: "Compare publisher versions",
    open: "Open ↗",
    source: "Source: {domain}",
    noRetainedLinks: "No retained links for this window.",
    keepUncertain: "Keep the signal uncertain unless you can verify it independently.",
    reviewGuardrail: "Choose “Real event” only when the news evidence appears to describe a physical flood. This label does not issue a public warning.",
    reviewRegion: "Review {region}",
    saving: "Saving…",
    noReviewSignals: "No candidate signals are waiting for review.",
    queueWillPopulate: "The queue will populate automatically when a reporting pattern passes every evidence gate.",
    decisionsStored: "Decisions are saved only on this PC in the local CrisisPulse review log.",
    connectingReviewLog: "Connecting to the local review log…",
    startLocalApi: "Start or restart the local API to save review decisions.",
    evaluationReadiness: "Evaluation readiness",
    measureBeforeMarket: "Measure before you market.",
    qualityDescription: "Human labels reveal whether unusual news signals are useful. CrisisPulse waits for at least {minimum} resolved decisions before displaying any rate as a product-quality result.",
    resolvedLabels: "{count} resolved labels",
    minimum: "{count} minimum",
    sampleProgress: "Resolved review sample progress",
    reviewedEventRate: "Reviewed event rate:",
    irrelevantRate: "Irrelevant-news rate: {rate}%. Human review is not external disaster verification.",
    moreDecisions: "{count} more resolved decisions needed.",
    uncertainMinimumNote: "“Uncertain” labels stay in the dataset but do not count toward the minimum.",
    downloadLabels: "Download labels (.csv)",
    savedReviewTotals: "Saved review totals",
    allLabels: "All labels",
    latestDecision: "Latest decision per signal",
    realEvents: "Real events",
    humanConfirmed: "Human-confirmed candidates",
    observedFalseSignals: "Observed false signals",
    needsEvidence: "Needs stronger evidence",
    forecastLab: "Forecast lab",
    forecastQuestion: "Will reporting spread in the next six hours?",
    targetDefinition: "At least {domains} independent source domains in any single hour during the next {hours} completed hours.",
    outcomesPending: "{count} outcomes pending",
    noForecastsPending: "No forecasts pending",
    completedWindows: "Completed outcome windows",
    chronologicalWork: "Available for chronological model work",
    mediaSpreadOutcomes: "Media-spread outcomes",
    noCompletedOutcomes: "No completed outcomes",
    historicalBaseRate: "{rate}% historical base rate",
    evaluationReadyAlerts: "Evaluation-ready alerts",
    baselineAndFuture: "Baseline complete plus six future hours",
    modelBenchmarkAria: "First chronological model benchmark",
    firstModel: "First chronological model",
    measuredHoldout: "Measured on later holdout hours.",
    modelDescription: "The alert threshold was chosen on an earlier validation period, then reported on a later {hours}-hour holdout that was not used for fitting or threshold selection. This is an exploratory benchmark—not production validation.",
    holdoutSummary: "{rows} holdout rows · {positives} positive outcomes",
    rankingQuality: "Ranking quality",
    averagePrecision: "Average precision",
    alertPrecision: "Alert precision",
    modelAlertsSpread: "Share of model alerts that spread",
    outcomeRecall: "Outcome recall",
    spreadOutcomesFound: "Share of spread outcomes found",
    falseAlertsDay: "False alerts / day",
    observedHoldout: "Observed in the later holdout",
    benchmarkPending: "First chronological benchmark pending.",
    benchmarkAfterRefresh: "It will appear after the local outcome and model refresh completes.",
    openForecastClocks: "Open forecast clocks",
    futureHidden: "Future data stays hidden until maturity",
    hoursRemaining: "{count}h remaining",
    atDetection: "At detection",
    storyOne: "{count} story",
    storyMany: "{count} stories",
    sourceDiversity: "Source diversity",
    domainOne: "{count} domain",
    domainMany: "{count} domains",
    outcomeCloses: "Outcome closes",
    modelScore: "Model score",
    clearsThreshold: "Clears the conservative alert threshold",
    doesNotClearThreshold: "Does not clear the alert threshold",
    belowThreshold: "Below the conservative {threshold} / 100 threshold",
    rankingNotProbability: "Ranking score—not a calibrated probability.",
    outcomeHoursObserved: "{observed} of {total} outcome hours observed",
    noCandidateForecasts: "No candidate forecasts are waiting for future data.",
    evaluationGate: "Evaluation gate",
    waitingByDesign: "Waiting by design",
    waitingExplanation: "The detector needs 168 prior hours, then each prediction needs six untouched future hours. Those two windows do not overlap yet.",
    windowsReady: "{count} windows ready",
    precisionRecall: "Precision: {precision} · Recall: {recall}",
    predictionTime: "Prediction time",
    hourZeroFeatures: "Hour 0 features only",
    outcomeWindow: "Outcome window",
    hoursRange: "Hours 1–{hours}",
    successThreshold: "Success threshold",
    latestEligibleHour: "Latest eligible hour",
    enoughEvidence: "Signals with enough evidence",
    candidateOne: "{count} candidate",
    candidateMany: "{count} candidates",
    normalCount: "{count} normal",
    region: "Region",
    stories: "Stories",
    domains: "Domains",
    baseline: "Baseline",
    score: "Score",
    signalStatus: "Signal status",
    normalStatus: "Normal",
    candidateStatus: "Candidate anomaly",
    zeroBaselineJump: "Zero-baseline jump",
    normalMeaning: "“Normal” means reporting was not unusually high compared with the prior seven days. It is not a statement about physical flood conditions.",
    scoringReadiness: "Scoring readiness",
    everyRow: "What happened to every row",
    buildingHistory: "Building history",
    belowEvidence: "Below evidence minimum",
    humanReviewActive: "Human review active",
    labelCandidates: "Turn candidates into labeled evidence",
    reviewFoundation: "Saved decisions create the foundation for measuring false positives and improving alert quality.",
    howItWorksAria: "How CrisisPulse works",
    howResultMade: "How this result was made",
    evidenceInDecisionsOut: "News evidence in. Explainable decisions out.",
    collect: "Collect",
    collectDetail: "15-minute GDELT updates",
    clean: "Clean",
    cleanDetail: "Remove repeats and weak matches",
    group: "Group",
    groupDetail: "Region, hour, and story",
    compare: "Compare",
    compareDetail: "Prior-hour median and spread",
    gate: "Gate",
    gateDetail: "Require history and source diversity",
    footerWarning: "detects unusual disaster-related news reporting. It is not an emergency warning system.",
    footerCost: "Local portfolio MVP · GDELT public data · $0 API cost",
    openArticleFrom: "Open article from {domain}",
  },
  {
    documentTitle: "CrisisPulse — Señales de reportes de inundaciones",
    documentDescription: "Detección explicable de anomalías en reportes de inundaciones con datos de noticias de GDELT.",
    dashboardHome: "Inicio del panel de CrisisPulse",
    primaryNavigation: "Navegación principal",
    dashboard: "Panel",
    admin: "Administración",
    liveConnected: "API en vivo conectada",
    verifiedSnapshot: "Instantánea local verificada",
    dashboardSections: "Secciones del panel",
    overview: "Resumen",
    coverage: "Cobertura",
    review: "Revisión",
    forecast: "Pronóstico",
    signals: "Señales",
    globalMonitor: "Monitor global de reportes de inundaciones",
    candidateHeadlineOne: "{count} señal inusual de reportes necesita revisión.",
    candidateHeadlineMany: "{count} señales inusuales de reportes necesitan revisión.",
    noUnusualSignals: "No hay señales inusuales de reportes en este momento.",
    reviewedWindow: "CrisisPulse revisó {window} de actividad de noticias de GDELT.",
    windowRange: "{start}–{end}",
    candidateLede: " Estos candidatos pasaron los filtros de historial y diversidad de fuentes y ahora necesitan revisión de evidencia.",
    cleanLede: " La última hora apta para puntuación se procesó sin alertas candidatas.",
    reviewRequired: "Se requiere revisar la evidencia.",
    behavingAsDesigned: "El sistema funciona según lo previsto.",
    candidateGuardrail: "Un candidato es un patrón inusual de noticias, no prueba de un desastre físico.",
    historyGuardrail: "El filtro de historial no convirtió la cobertura normal en una alerta.",
    currentWatchStatus: "Estado actual de vigilancia",
    currentWatch: "Vigilancia actual",
    candidateAnomalies: "Anomalías candidatas",
    minimumHistory: "Historial mínimo",
    hours: "{count} horas",
    minimumEvidence: "Evidencia mínima",
    storiesDomains: "{stories} historias · {domains} dominios",
    alertThreshold: "Umbral de alerta",
    thresholdDefinition: "z ≥ {threshold} o un salto con base cero que supera los filtros",
    dataCoverage: "Cobertura de datos",
    retainedArticles: "Artículos sobre inundaciones conservados",
    duplicateRemoval: "Después de eliminar duplicados exactos",
    regionsObserved: "Regiones observadas",
    regionTypes: "Regiones identificadas y sin resolver",
    hourlyWindows: "Ventanas por hora",
    hourlyStoryGroups: "Grupos de historias por hora",
    groupsDefinition: "Distintos dentro de cada región y hora",
    publisherEvidence: "Evidencia de publicaciones",
    latestCoverage: "Cobertura reciente de inundaciones",
    latestCoverageDescription: "Reportes recientes que pasaron las verificaciones de CrisisPulse sobre inundaciones. Estos enlaces son evidencia, no confirmación automática de un incidente físico.",
    recentGroupsAria: "{count} grupos de historias recientes",
    recentGroupOne: "grupo de historias reciente",
    recentGroupMany: "grupos de historias recientes",
    multiSourceCoverage: "Cobertura de varias fuentes",
    corroboratedCoverage: "Cobertura corroborada",
    singlePublisher: "Una publicación",
    locationUnresolved: "Ubicación sin resolver",
    independentPublishers: "{count} publicaciones independientes",
    readPublisherReport: "Leer reporte de la publicación",
    noRecentCoverage: "No hay cobertura reciente apta en esta ventana.",
    coverageWillFill: "El contenido aparecerá automáticamente cuando lleguen los próximos reportes verificados sobre inundaciones.",
    humanValidation: "Validación humana",
    reviewQueue: "Cola de revisión",
    reviewQueueDescription: "Clasifica reportes inusuales para que CrisisPulse pueda separar eventos creíbles de cobertura irrelevante y evidencia ambigua.",
    labeledProgress: "{reviewed} de {total} clasificados",
    realEvent: "Evento real",
    irrelevantNews: "Noticia irrelevante",
    irrelevant: "Irrelevante",
    uncertain: "Incierto",
    savedReview: "Se guardó “{decision}” para {region}.",
    saveReviewFailed: "No se pudo guardar la decisión. Verifica que la API local esté funcionando.",
    needsReview: "Necesita revisión",
    storyGroups: "Grupos de historias",
    sourceDomains: "Dominios fuente",
    priorBaseline: "Base anterior",
    robustScore: "Puntuación robusta",
    sourceEvidenceFor: "Evidencia de fuentes para {region}",
    directEvidence: "Evidencia directa de publicaciones",
    sourceLinksByStory: "Enlaces de fuentes por historia distinta",
    groupOne: "grupo",
    groupMany: "grupos",
    evidenceNote: "Las etiquetas de GDELT son un punto de partida, no una prueba. Los conflictos claros con un titular derivado de la URL se degradan y no pueden crear una alerta.",
    storyNumber: "Historia {number}",
    publisherLinkOne: "{count} enlace de publicación",
    publisherLinkMany: "{count} enlaces de publicaciones",
    noSafeLink: "No se conservó un enlace seguro de la publicación",
    gdeltTag: "Etiqueta GDELT: {theme}",
    compareVersions: "Comparar versiones de publicaciones",
    open: "Abrir ↗",
    source: "Fuente: {domain}",
    noRetainedLinks: "No hay enlaces conservados para esta ventana.",
    keepUncertain: "Mantén la señal como incierta a menos que puedas verificarla de forma independiente.",
    reviewGuardrail: "Elige “Evento real” solo cuando la evidencia periodística parezca describir una inundación física. Esta etiqueta no emite una alerta pública.",
    reviewRegion: "Revisar {region}",
    saving: "Guardando…",
    noReviewSignals: "No hay señales candidatas pendientes de revisión.",
    queueWillPopulate: "La cola se llenará automáticamente cuando un patrón de reportes pase todos los filtros de evidencia.",
    decisionsStored: "Las decisiones se guardan únicamente en esta PC, en el registro local de revisión de CrisisPulse.",
    connectingReviewLog: "Conectando con el registro local de revisión…",
    startLocalApi: "Inicia o reinicia la API local para guardar decisiones de revisión.",
    evaluationReadiness: "Preparación para la evaluación",
    measureBeforeMarket: "Mide antes de promocionar.",
    qualityDescription: "Las etiquetas humanas muestran si las señales inusuales son útiles. CrisisPulse espera al menos {minimum} decisiones resueltas antes de mostrar una tasa como resultado de calidad del producto.",
    resolvedLabels: "{count} etiquetas resueltas",
    minimum: "mínimo de {count}",
    sampleProgress: "Progreso de la muestra de revisiones resueltas",
    reviewedEventRate: "Tasa de eventos revisados:",
    irrelevantRate: "Tasa de noticias irrelevantes: {rate}%. La revisión humana no es una verificación externa del desastre.",
    moreDecisions: "Se necesitan {count} decisiones resueltas más.",
    uncertainMinimumNote: "Las etiquetas “Incierto” permanecen en los datos, pero no cuentan para el mínimo.",
    downloadLabels: "Descargar etiquetas (.csv)",
    savedReviewTotals: "Totales de revisiones guardadas",
    allLabels: "Todas las etiquetas",
    latestDecision: "Última decisión por señal",
    realEvents: "Eventos reales",
    humanConfirmed: "Candidatos confirmados por una persona",
    observedFalseSignals: "Señales falsas observadas",
    needsEvidence: "Necesita evidencia más sólida",
    forecastLab: "Laboratorio de pronósticos",
    forecastQuestion: "¿Se extenderán los reportes en las próximas seis horas?",
    targetDefinition: "Al menos {domains} dominios fuente independientes en una misma hora durante las próximas {hours} horas completadas.",
    outcomesPending: "{count} resultados pendientes",
    noForecastsPending: "No hay pronósticos pendientes",
    completedWindows: "Ventanas de resultados completadas",
    chronologicalWork: "Disponibles para trabajo cronológico del modelo",
    mediaSpreadOutcomes: "Resultados de propagación en medios",
    noCompletedOutcomes: "No hay resultados completados",
    historicalBaseRate: "{rate}% de tasa histórica base",
    evaluationReadyAlerts: "Alertas listas para evaluación",
    baselineAndFuture: "Base completa más seis horas futuras",
    modelBenchmarkAria: "Primera evaluación cronológica del modelo",
    firstModel: "Primer modelo cronológico",
    measuredHoldout: "Medido en horas de reserva posteriores.",
    modelDescription: "El umbral de alerta se eligió en un período de validación anterior y luego se reportó en una reserva posterior de {hours} horas que no se utilizó para el ajuste ni para seleccionar el umbral. Es una evaluación exploratoria, no una validación para producción.",
    holdoutSummary: "{rows} filas de reserva · {positives} resultados positivos",
    rankingQuality: "Calidad de clasificación",
    averagePrecision: "Precisión promedio",
    alertPrecision: "Precisión de alertas",
    modelAlertsSpread: "Proporción de alertas del modelo que se extendieron",
    outcomeRecall: "Cobertura de resultados",
    spreadOutcomesFound: "Proporción de resultados extendidos encontrados",
    falseAlertsDay: "Alertas falsas / día",
    observedHoldout: "Observado en la reserva posterior",
    benchmarkPending: "Primera evaluación cronológica pendiente.",
    benchmarkAfterRefresh: "Aparecerá cuando termine la actualización local de resultados y del modelo.",
    openForecastClocks: "Relojes de pronóstico abiertos",
    futureHidden: "Los datos futuros permanecen ocultos hasta la madurez",
    hoursRemaining: "quedan {count} h",
    atDetection: "Al detectar",
    storyOne: "{count} historia",
    storyMany: "{count} historias",
    sourceDiversity: "Diversidad de fuentes",
    domainOne: "{count} dominio",
    domainMany: "{count} dominios",
    outcomeCloses: "Cierre del resultado",
    modelScore: "Puntuación del modelo",
    clearsThreshold: "Supera el umbral de alerta conservador",
    doesNotClearThreshold: "No supera el umbral de alerta",
    belowThreshold: "Por debajo del umbral conservador de {threshold} / 100",
    rankingNotProbability: "Puntuación de clasificación, no una probabilidad calibrada.",
    outcomeHoursObserved: "{observed} de {total} horas de resultado observadas",
    noCandidateForecasts: "No hay pronósticos candidatos esperando datos futuros.",
    evaluationGate: "Filtro de evaluación",
    waitingByDesign: "Espera prevista",
    waitingExplanation: "El detector necesita 168 horas anteriores y luego cada predicción necesita seis horas futuras intactas. Esas dos ventanas aún no se superponen.",
    windowsReady: "{count} ventanas listas",
    precisionRecall: "Precisión: {precision} · Cobertura: {recall}",
    predictionTime: "Momento de predicción",
    hourZeroFeatures: "Solo variables de la hora 0",
    outcomeWindow: "Ventana de resultados",
    hoursRange: "Horas 1–{hours}",
    successThreshold: "Umbral de éxito",
    latestEligibleHour: "Última hora apta",
    enoughEvidence: "Señales con evidencia suficiente",
    candidateOne: "{count} candidato",
    candidateMany: "{count} candidatos",
    normalCount: "{count} normales",
    region: "Región",
    stories: "Historias",
    domains: "Dominios",
    baseline: "Base",
    score: "Puntuación",
    signalStatus: "Estado de señal",
    normalStatus: "Normal",
    candidateStatus: "Anomalía candidata",
    zeroBaselineJump: "Salto con base cero",
    normalMeaning: "“Normal” significa que los reportes no fueron inusualmente altos frente a los siete días anteriores. No describe las condiciones físicas de inundación.",
    scoringReadiness: "Preparación de puntuación",
    everyRow: "Qué ocurrió con cada fila",
    buildingHistory: "Creando historial",
    belowEvidence: "Por debajo de la evidencia mínima",
    humanReviewActive: "Revisión humana activa",
    labelCandidates: "Convierte candidatos en evidencia etiquetada",
    reviewFoundation: "Las decisiones guardadas crean la base para medir falsos positivos y mejorar la calidad de las alertas.",
    howItWorksAria: "Cómo funciona CrisisPulse",
    howResultMade: "Cómo se obtuvo este resultado",
    evidenceInDecisionsOut: "Entra evidencia periodística. Salen decisiones explicables.",
    collect: "Recopilar",
    collectDetail: "Actualizaciones de GDELT cada 15 minutos",
    clean: "Limpiar",
    cleanDetail: "Eliminar repeticiones y coincidencias débiles",
    group: "Agrupar",
    groupDetail: "Región, hora e historia",
    compare: "Comparar",
    compareDetail: "Mediana y dispersión de horas anteriores",
    gate: "Filtrar",
    gateDetail: "Exigir historial y diversidad de fuentes",
    footerWarning: "detecta reportes inusuales de noticias relacionadas con desastres. No es un sistema de alerta de emergencia.",
    footerCost: "MVP local de portafolio · datos públicos de GDELT · costo de API: $0",
    openArticleFrom: "Abrir artículo de {domain}",
  },
);

const formatScore = (value: number | null) => {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`.replace("-", "−");
};
const headlineAcronyms: Record<string, string> = {
  abc: "ABC",
  ai: "AI",
  bbc: "BBC",
  cbs: "CBS",
  cnn: "CNN",
  csc: "CSC",
  fema: "FEMA",
  gdelt: "GDELT",
  nasa: "NASA",
  nbc: "NBC",
  nj: "NJ",
  noaa: "NOAA",
  nws: "NWS",
  nyc: "NYC",
  usa: "USA",
  ust: "UST",
};
const preserveHeadlineAcronyms = (value: string, includeUS = false) =>
  value.replace(/\b[A-Za-z][A-Za-z0-9]*\b/g, (word) => {
    const lowered = word.toLowerCase();
    if (includeUS && lowered === "us") return "US";
    return headlineAcronyms[lowered] ?? word;
  });
const sourceLabel = (source: EvidenceSource, openArticleFrom: string) => {
  try {
    const parsed = new URL(source.url);
    const segments = parsed.pathname.split("/").filter(Boolean).reverse();
    for (const segment of segments) {
      const decoded = decodeURIComponent(segment)
        .replace(/\.(?:html?|aspx?|php)$/i, "")
        .trim();
      if (!decoded || /^\d+$/.test(decoded)) continue;
      if (/^(?:article[-_]?)?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(decoded)) continue;
      const words = decoded.match(/[A-Za-zÀ-ÖØ-öø-ÿ]+/g) ?? [];
      if (words.length < 2) continue;
      const readable = decoded.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
      if (readable) {
        const titleCased = readable.replace(/\b\w/g, (letter) => letter.toUpperCase());
        return preserveHeadlineAcronyms(titleCased, true);
      }
    }
    return formatMessage(openArticleFrom, { domain: source.domain });
  } catch {
    return source.domain;
  }
};
const safePublisherURL = (value: string) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
};
const publisherDomain = (source: EvidenceSource) => {
  const safeURL = safePublisherURL(source.url);
  if (!safeURL) return null;
  return new URL(safeURL).hostname.replace(/^www\./i, "");
};
const storyHeadline = (story: EvidenceStory, source: EvidenceSource, openArticleFrom: string) =>
  story.title
    ? preserveHeadlineAcronyms(story.title)
    : sourceLabel(source, openArticleFrom);
const readableTheme = (theme: string) => {
  const readable = theme
    .replace(/^NATURAL_DISASTER_/, "")
    .replaceAll("_", " ")
    .toLowerCase();
  return readable.charAt(0).toUpperCase() + readable.slice(1);
};
const signalID = (signal: Signal) => `${signal.code}|${signal.window_start}`;
const formatSignalScore = (signal: Signal, zeroBaselineJump: string) =>
  signal.score === null && signal.status === "candidate_anomaly"
    ? zeroBaselineJump
    : formatScore(signal.score);
const parseUTCDate = (value: string) => new Date(value.endsWith("Z") ? value : `${value}Z`);
const formatWindow = (value: string, localeTag: "en-US" | "es-US") => {
  const date = parseUTCDate(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(localeTag, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
};

const formatDateRange = (
  startValue: string,
  endValue: string,
  localeTag: "en-US" | "es-US",
) => {
  const start = parseUTCDate(startValue);
  const end = parseUTCDate(endValue);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return `${startValue}–${endValue}`;
  const formatter = new Intl.DateTimeFormat(localeTag, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  if (typeof formatter.formatRange === "function") return formatter.formatRange(start, end);
  return `${formatter.format(start)}–${formatter.format(end)}`;
};

export default function Home() {
  const { locale, localeTag } = useLocale();
  const t = messages[locale];
  const formatNumber = (value: number) => value.toLocaleString(localeTag);
  const formatDecimal = (value: number, digits = 1) => value.toLocaleString(localeTag, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
  const formatPercent = (value: number, digits = 0) => `${formatDecimal(value * 100, digits)}%`;
  const reviewOptions: Array<{
    value: ReviewDecision;
    label: string;
    shortLabel: string;
    tone: string;
  }> = [
    { value: "confirmed_event", label: t.realEvent, shortLabel: t.realEvent, tone: "confirmed" },
    { value: "irrelevant_news", label: t.irrelevantNews, shortLabel: t.irrelevant, tone: "irrelevant" },
    { value: "uncertain", label: t.uncertain, shortLabel: t.uncertain, tone: "uncertain" },
  ];
  const statusRows = [
    { key: "insufficient_history", label: t.buildingHistory, tone: "waiting" },
    { key: "below_minimum_support", label: t.belowEvidence, tone: "quiet" },
    { key: "normal", label: t.normalStatus, tone: "normal" },
    { key: "candidate_anomaly", label: t.candidateStatus, tone: "alert" },
  ] as const;
  const [dashboardData, setDashboardData] = useState<DashboardData>(
    bundledDashboardData as DashboardData,
  );
  const [dataSource, setDataSource] = useState<"api" | "snapshot">("snapshot");
  const [reviews, setReviews] = useState<Record<string, ReviewRecord>>({});
  const [reviewSummary, setReviewSummary] = useState<ReviewSummary | null>(null);
  const [reviewConnection, setReviewConnection] = useState<"loading" | "ready" | "unavailable">("loading");
  const [savingReview, setSavingReview] = useState<{ signalID: string; decision: ReviewDecision } | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const { snapshot, signals, parameters, status_counts: statusCounts, forecast } = dashboardData;
  const windowLabel = formatDateRange(snapshot.window_start, snapshot.window_end, localeTag);
  const targetDefinition = formatMessage(t.targetDefinition, {
    domains: formatNumber(forecast.target.domain_threshold),
    hours: formatNumber(forecast.target.horizon_hours),
  });
  const latestCoverage = (Array.isArray(dashboardData.latest_coverage)
    ? dashboardData.latest_coverage
    : [])
    .map((story) => ({
      ...story,
      sources: Array.isArray(story.sources)
        ? story.sources.filter((source) => safePublisherURL(source.url))
        : [],
    }))
    .filter((story) => story.sources.length > 0)
    .slice(0, 6);
  const hasCandidates = snapshot.candidates > 0;
  const candidateSignals = signals.filter((signal) => signal.status === "candidate_anomaly");
  const reviewedCount = candidateSignals.filter((signal) => reviews[signalID(signal)]).length;
  const sampleProgress = reviewSummary
    ? Math.min(100, (reviewSummary.resolved_reviews / reviewSummary.minimum_sample) * 100)
    : 0;
  const outcomeBaseRate = forecast.eligible_windows > 0
    ? forecast.positive_outcomes / forecast.eligible_windows
    : null;
  const modelPredictions = new Map(
    forecast.model.pending_predictions.map((prediction) => [
      `${prediction.region_code}|${prediction.window_start}`,
      prediction,
    ]),
  );
  const barWidth = (count: number) =>
    count <= 0 || snapshot.scored_rows <= 0
      ? "0%"
      : `${Math.min(100, Math.max(3, (count / snapshot.scored_rows) * 100))}%`;

  useEffect(() => {
    document.title = t.documentTitle;
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = t.documentDescription;
  }, [t.documentDescription, t.documentTitle]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(snapshotURL, { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        return response.json() as Promise<DashboardData>;
      })
      .then((nextData) => {
        if (!nextData.snapshot || !Array.isArray(nextData.signals)) {
          throw new Error("API response is missing dashboard fields");
        }
        setDashboardData((current) => ({
          ...nextData,
          latest_coverage: Array.isArray(nextData.latest_coverage)
            ? nextData.latest_coverage
            : current.latest_coverage,
        }));
        setDataSource("api");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setDataSource("snapshot");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(reviewsURL, { cache: "no-store", signal: controller.signal }),
      fetch(reviewSummaryURL, { cache: "no-store", signal: controller.signal }),
    ])
      .then(async ([reviewsResponse, summaryResponse]) => {
        if (!reviewsResponse.ok || !summaryResponse.ok) {
          throw new Error("Review API is unavailable");
        }
        return Promise.all([
          reviewsResponse.json() as Promise<ReviewsResponse>,
          summaryResponse.json() as Promise<ReviewSummary>,
        ]);
      })
      .then(([payload, summary]) => {
        const latest = Object.fromEntries(
          payload.reviews.map((review) => [review.signal_id, review]),
        );
        setReviews(latest);
        setReviewSummary(summary);
        setReviewConnection("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setReviewConnection("unavailable");
        }
      });
    return () => controller.abort();
  }, []);

  const saveReview = async (signal: Signal, decision: ReviewDecision) => {
    const id = signalID(signal);
    setSavingReview({ signalID: id, decision });
    setReviewNotice(null);
    try {
      const response = await fetch(reviewsURL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          region_code: signal.code,
          window_start: signal.window_start,
          decision,
        }),
      });
      if (!response.ok) throw new Error(`Review API returned ${response.status}`);
      const payload = await response.json() as ReviewResponse;
      setReviews((current) => ({ ...current, [payload.review.signal_id]: payload.review }));
      const summaryResponse = await fetch(reviewSummaryURL, { cache: "no-store" });
      if (summaryResponse.ok) {
        setReviewSummary(await summaryResponse.json() as ReviewSummary);
      }
      setReviewConnection("ready");
      const choice = reviewOptions.find((option) => option.value === decision);
      setReviewNotice(formatMessage(t.savedReview, {
        decision: choice?.label ?? decision,
        region: signal.region,
      }));
    } catch {
      setReviewConnection("unavailable");
      setReviewNotice(t.saveReviewFailed);
    } finally {
      setSavingReview(null);
    }
  };

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label={t.dashboardHome}>
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>CrisisPulse</span>
        </a>
        <nav className="header-nav" aria-label={t.primaryNavigation}>
          <Link className="active" href="/">{t.dashboard}</Link>
          <Link href="/admin">{t.admin}</Link>
        </nav>
        <LanguageSwitcher />
        <div className="header-meta">
          <span className={dataSource === "api" ? "live-dot" : "live-dot snapshot"} aria-hidden="true" />
          {dataSource === "api" ? t.liveConnected : t.verifiedSnapshot}
          <strong>{formatWindow(snapshot.window_end, localeTag)}</strong>
        </div>
      </header>

      <nav className="mobile-section-nav" aria-label={t.dashboardSections}>
        <a href="#top">{t.overview}</a>
        <a href="#coverage">{t.coverage}</a>
        <a href="#review">{t.review}</a>
        <a href="#forecast">{t.forecast}</a>
        <a href="#signals">{t.signals}</a>
      </nav>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">{t.globalMonitor}</p>
          <h1>
            {hasCandidates
              ? formatMessage(snapshot.candidates === 1 ? t.candidateHeadlineOne : t.candidateHeadlineMany, {
                count: formatNumber(snapshot.candidates),
              })
              : t.noUnusualSignals}
          </h1>
          <p className="lede">
            {formatMessage(t.reviewedWindow, { window: windowLabel })}
            {hasCandidates
              ? t.candidateLede
              : t.cleanLede}
          </p>
          <div className="notice" role="status">
            <span className={hasCandidates ? "notice-icon alert" : "notice-icon"} aria-hidden="true">
              {hasCandidates ? "!" : "✓"}
            </span>
            <span>
              <strong>{hasCandidates ? t.reviewRequired : t.behavingAsDesigned}</strong>
              {hasCandidates
                ? t.candidateGuardrail
                : t.historyGuardrail}
            </span>
          </div>
        </div>

        <aside className="watch-panel" aria-label={t.currentWatchStatus}>
          <p className="panel-label">{t.currentWatch}</p>
          <div className="watch-count">{formatNumber(snapshot.candidates)}</div>
          <p className="watch-title">{t.candidateAnomalies}</p>
          <div className="watch-rule" />
          <dl className="watch-details">
            <div><dt>{t.minimumHistory}</dt><dd>{formatMessage(t.hours, { count: formatNumber(parameters.minimum_history_hours) })}</dd></div>
            <div><dt>{t.minimumEvidence}</dt><dd>{formatMessage(t.storiesDomains, { stories: formatNumber(parameters.minimum_stories), domains: formatNumber(parameters.minimum_domains) })}</dd></div>
            <div><dt>{t.alertThreshold}</dt><dd>{formatMessage(t.thresholdDefinition, { threshold: formatDecimal(parameters.z_threshold) })}</dd></div>
          </dl>
        </aside>
      </section>

      <section className="metrics" aria-label={t.dataCoverage}>
        <article>
          <p>{t.retainedArticles}</p>
          <strong>{formatNumber(snapshot.clean_articles)}</strong>
          <span>{t.duplicateRemoval}</span>
        </article>
        <article>
          <p>{t.regionsObserved}</p>
          <strong>{formatNumber(snapshot.regions)}</strong>
          <span>{t.regionTypes}</span>
        </article>
        <article>
          <p>{t.hourlyWindows}</p>
          <strong>{formatNumber(snapshot.hours)}</strong>
          <span>{windowLabel}</span>
        </article>
        <article>
          <p>{t.hourlyStoryGroups}</p>
          <strong>{formatNumber(snapshot.story_groups)}</strong>
          <span>{t.groupsDefinition}</span>
        </article>
      </section>

      <section className="coverage-section" id="coverage" aria-labelledby="coverage-heading">
        <div className="coverage-heading">
          <div>
            <p className="eyebrow">{t.publisherEvidence}</p>
            <h2 id="coverage-heading">{t.latestCoverage}</h2>
            <p>{t.latestCoverageDescription}</p>
          </div>
          <div className="coverage-count" aria-label={formatMessage(t.recentGroupsAria, { count: formatNumber(latestCoverage.length) })}>
            <strong>{formatNumber(latestCoverage.length)}</strong>
            <span>{latestCoverage.length === 1 ? t.recentGroupOne : t.recentGroupMany}</span>
          </div>
        </div>

        {latestCoverage.length > 0 ? (
          <div className="coverage-grid">
            {latestCoverage.map((story) => {
              const primarySource = story.sources[0];
              const primaryURL = safePublisherURL(primarySource.url);
              const domains = Array.from(new Set(
                story.sources.map(publisherDomain).filter((domain): domain is string => Boolean(domain)),
              ));
              return (
                <article className="coverage-card" key={`${story.story_id}-${story.seen_at}`}>
                  <header>
                    <span className={domains.length > 1 ? "coverage-badge corroborated" : "coverage-badge"}>
                      {domains.length >= 3
                        ? t.multiSourceCoverage
                        : domains.length === 2
                          ? t.corroboratedCoverage
                          : t.singlePublisher}
                    </span>
                    <time dateTime={story.seen_at}>{formatWindow(story.seen_at, localeTag)}</time>
                  </header>
                  <a className="coverage-title" href={primaryURL ?? undefined} rel="noopener noreferrer" target="_blank">
                    {storyHeadline(story, primarySource, t.openArticleFrom)} <span aria-hidden="true">↗</span>
                  </a>
                  <div className="coverage-context">
                    <span>{story.location || t.locationUnresolved}</span>
                    {story.themes.slice(0, 2).map((theme) => (
                      <span key={theme}>{readableTheme(theme)}</span>
                    ))}
                  </div>
                  <footer className="coverage-source">
                    <span>{domains.length > 1 ? formatMessage(t.independentPublishers, { count: formatNumber(domains.length) }) : domains[0]}</span>
                    <a href={primaryURL ?? undefined} rel="noopener noreferrer" target="_blank">{t.readPublisherReport}</a>
                  </footer>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="coverage-empty">
            <span aria-hidden="true">✓</span>
            <div>
              <strong>{t.noRecentCoverage}</strong>
              <p>{t.coverageWillFill}</p>
            </div>
          </div>
        )}
      </section>

      <section className="review-section" id="review" aria-labelledby="review-heading">
        <div className="review-heading">
          <div>
            <p className="eyebrow">{t.humanValidation}</p>
            <h2 id="review-heading">{t.reviewQueue}</h2>
            <p>{t.reviewQueueDescription}</p>
          </div>
          <span className={reviewedCount === candidateSignals.length && candidateSignals.length > 0 ? "review-progress complete" : "review-progress"}>
            {formatMessage(t.labeledProgress, { reviewed: formatNumber(reviewedCount), total: formatNumber(candidateSignals.length) })}
          </span>
        </div>

        {reviewNotice ? <p className="review-notice" role="status">{reviewNotice}</p> : null}

        {candidateSignals.length > 0 ? (
          <div className="review-grid">
            {candidateSignals.map((signal) => {
              const id = signalID(signal);
              const currentReview = reviews[id];
              const currentOption = reviewOptions.find(
                (option) => option.value === currentReview?.decision,
              );
              const isSaving = savingReview?.signalID === id;
              const evidence = Array.isArray(signal.evidence) ? signal.evidence : [];
              return (
                <article className="review-card" key={id}>
                  <header>
                    <div>
                      <span className="review-code">{signal.code}</span>
                      <h3>{signal.region}</h3>
                      <time dateTime={signal.window_start}>{formatWindow(signal.window_start, localeTag)}</time>
                    </div>
                    <span className={currentOption ? `decision-chip ${currentOption.tone}` : "decision-chip pending"}>
                      {currentOption?.shortLabel ?? t.needsReview}
                    </span>
                  </header>
                  <dl className="review-evidence">
                    <div><dt>{t.storyGroups}</dt><dd>{formatNumber(signal.stories)}</dd></div>
                    <div><dt>{t.sourceDomains}</dt><dd>{formatNumber(signal.domains)}</dd></div>
                    <div><dt>{t.priorBaseline}</dt><dd>{signal.baseline === null ? "—" : formatDecimal(signal.baseline)}</dd></div>
                    <div><dt>{t.robustScore}</dt><dd>{formatSignalScore(signal, t.zeroBaselineJump)}</dd></div>
                  </dl>
                  <section className="source-evidence" aria-label={formatMessage(t.sourceEvidenceFor, { region: signal.region })}>
                    <div className="source-evidence-heading">
                      <div>
                        <span>{t.directEvidence}</span>
                        <strong>{t.sourceLinksByStory}</strong>
                      </div>
                      <b>{formatNumber(evidence.length)} {evidence.length === 1 ? t.groupOne : t.groupMany}</b>
                    </div>
                    <p className="source-evidence-note">{t.evidenceNote}</p>
                    {evidence.length > 0 ? (
                      <ol className="evidence-story-list">
                        {evidence.map((story, storyIndex) => {
                          const publisherSources = (Array.isArray(story.sources) ? story.sources : [])
                            .filter((source) => safePublisherURL(source.url));
                          const primarySource = publisherSources[0];
                          return (
                            <li className="evidence-story" key={story.story_id}>
                              <div className="evidence-story-header">
                                <span>{formatMessage(t.storyNumber, { number: String(storyIndex + 1).padStart(2, "0") })}</span>
                                <small>{formatMessage(publisherSources.length === 1 ? t.publisherLinkOne : t.publisherLinkMany, { count: formatNumber(publisherSources.length) })}</small>
                              </div>
                              {primarySource ? (
                                <a
                                  className="evidence-primary-link"
                                  href={safePublisherURL(primarySource.url) ?? undefined}
                                  rel="noopener noreferrer"
                                  target="_blank"
                                >
                                  {storyHeadline(story, primarySource, t.openArticleFrom)} <span aria-hidden="true">↗</span>
                                </a>
                              ) : (
                                <span className="evidence-primary-link unavailable">
                                  {t.noSafeLink}
                                </span>
                              )}
                              <div className="evidence-context">
                                {story.location ? <span>{story.location}</span> : null}
                                {(story.themes ?? []).slice(0, 2).map((theme) => (
                                  <span key={theme}>{formatMessage(t.gdeltTag, { theme: readableTheme(theme) })}</span>
                                ))}
                              </div>
                              {publisherSources.length > 1 ? (
                                <details>
                                  <summary>{t.compareVersions}</summary>
                                  <ul className="source-list">
                                    {publisherSources.map((source) => (
                                      <li key={source.url}>
                                        <a href={safePublisherURL(source.url) ?? undefined} rel="noopener noreferrer" target="_blank">
                                          <span>{source.domain}</span><b>{t.open}</b>
                                        </a>
                                      </li>
                                    ))}
                                  </ul>
                                </details>
                              ) : primarySource ? (
                                <p className="single-source">{formatMessage(t.source, { domain: primarySource.domain })}</p>
                              ) : null}
                            </li>
                          );
                        })}
                      </ol>
                    ) : (
                      <div className="source-evidence-empty">
                        <strong>{t.noRetainedLinks}</strong>
                        <span>{t.keepUncertain}</span>
                      </div>
                    )}
                  </section>
                  <p className="review-guardrail">{t.reviewGuardrail}</p>
                  <div className="review-actions" aria-label={formatMessage(t.reviewRegion, { region: signal.region })}>
                    {reviewOptions.map((option) => (
                      <button
                        className={`review-button ${option.tone}${currentReview?.decision === option.value ? " selected" : ""}`}
                        disabled={reviewConnection !== "ready" || isSaving || dataSource !== "api"}
                        key={option.value}
                        onClick={() => void saveReview(signal, option.value)}
                        type="button"
                        aria-pressed={currentReview?.decision === option.value}
                      >
                        {isSaving && savingReview?.decision === option.value ? t.saving : option.label}
                      </button>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="review-empty">
            <span aria-hidden="true">✓</span>
            <div>
              <strong>{t.noReviewSignals}</strong>
              <p>{t.queueWillPopulate}</p>
            </div>
          </div>
        )}

        <p className="review-storage">
          {reviewConnection === "ready"
            ? t.decisionsStored
            : reviewConnection === "loading"
              ? t.connectingReviewLog
              : t.startLocalApi}
        </p>
      </section>

      <section className="quality-section" aria-labelledby="quality-heading">
        <article className="quality-story">
          <p className="eyebrow">{t.evaluationReadiness}</p>
          <h2 id="quality-heading">{t.measureBeforeMarket}</h2>
          <p>{formatMessage(t.qualityDescription, { minimum: formatNumber(reviewSummary?.minimum_sample ?? 20) })}</p>
          <div className="quality-progress-copy">
            <strong>{formatMessage(t.resolvedLabels, { count: formatNumber(reviewSummary?.resolved_reviews ?? 0) })}</strong>
            <span>{formatMessage(t.minimum, { count: formatNumber(reviewSummary?.minimum_sample ?? 20) })}</span>
          </div>
          <span
            aria-label={t.sampleProgress}
            aria-valuemax={reviewSummary?.minimum_sample ?? 20}
            aria-valuemin={0}
            aria-valuenow={reviewSummary?.resolved_reviews ?? 0}
            className="quality-progress-bar"
            role="progressbar"
          >
            <i style={{ width: `${sampleProgress}%` }} />
          </span>
          {reviewSummary?.status === "sample_ready" ? (
            <p className="quality-result ready">
              {t.reviewedEventRate} <strong>{formatPercent(reviewSummary.confirmed_event_rate ?? 0)}</strong>
              <span>{formatMessage(t.irrelevantRate, { rate: formatDecimal((reviewSummary.irrelevant_news_rate ?? 0) * 100, 0) })}</span>
            </p>
          ) : (
            <p className="quality-result">
              <strong>{formatMessage(t.moreDecisions, { count: formatNumber(reviewSummary?.remaining_to_sample ?? 20) })}</strong>
              <span>{t.uncertainMinimumNote}</span>
            </p>
          )}
          {reviewConnection === "ready" ? (
            <a
              className="export-link"
              download="crisispulse-reviews.csv"
              href={reviewExportURL}
            >
              {t.downloadLabels} <span aria-hidden="true">↓</span>
            </a>
          ) : (
            <span aria-disabled="true" className="export-link disabled">
              {t.downloadLabels} <span aria-hidden="true">↓</span>
            </span>
          )}
        </article>

        <div className="quality-metrics" aria-label={t.savedReviewTotals}>
          <article>
            <span>{t.allLabels}</span>
            <strong>{formatNumber(reviewSummary?.total_reviews ?? 0)}</strong>
            <small>{t.latestDecision}</small>
          </article>
          <article className="confirmed">
            <span>{t.realEvents}</span>
            <strong>{formatNumber(reviewSummary?.confirmed_events ?? 0)}</strong>
            <small>{t.humanConfirmed}</small>
          </article>
          <article className="irrelevant">
            <span>{t.irrelevantNews}</span>
            <strong>{formatNumber(reviewSummary?.irrelevant_news ?? 0)}</strong>
            <small>{t.observedFalseSignals}</small>
          </article>
          <article className="uncertain">
            <span>{t.uncertain}</span>
            <strong>{formatNumber(reviewSummary?.uncertain ?? 0)}</strong>
            <small>{t.needsEvidence}</small>
          </article>
        </div>
      </section>

      <section className="forecast-section" id="forecast" aria-labelledby="forecast-heading">
        <div className="forecast-heading">
          <div>
            <p className="eyebrow">{t.forecastLab}</p>
            <h2 id="forecast-heading">{t.forecastQuestion}</h2>
            <p>{targetDefinition}</p>
          </div>
          <span className={forecast.pending_predictions.length > 0 ? "forecast-status pending" : "forecast-status"}>
            {forecast.pending_predictions.length > 0
              ? formatMessage(t.outcomesPending, { count: formatNumber(forecast.pending_predictions.length) })
              : t.noForecastsPending}
          </span>
        </div>

        <div className="forecast-summary-grid">
          <article>
            <span>{t.completedWindows}</span>
            <strong>{formatNumber(forecast.eligible_windows)}</strong>
            <small>{t.chronologicalWork}</small>
          </article>
          <article>
            <span>{t.mediaSpreadOutcomes}</span>
            <strong>{formatNumber(forecast.positive_outcomes)}</strong>
            <small>{outcomeBaseRate === null
              ? t.noCompletedOutcomes
              : formatMessage(t.historicalBaseRate, { rate: formatDecimal(outcomeBaseRate * 100, 2) })}</small>
          </article>
          <article>
            <span>{t.evaluationReadyAlerts}</span>
            <strong>{formatNumber(forecast.evaluated_predictions)}</strong>
            <small>{t.baselineAndFuture}</small>
          </article>
        </div>

        {forecast.model.status === "ready" ? (
          <section className="model-benchmark" aria-label={t.modelBenchmarkAria}>
            <div className="model-benchmark-intro">
              <p className="eyebrow">{t.firstModel}</p>
              <h3>{t.measuredHoldout}</h3>
              <p>{formatMessage(t.modelDescription, { hours: formatNumber(forecast.model.test_hours) })}</p>
              <span>{formatMessage(t.holdoutSummary, {
                rows: formatNumber(forecast.model.test_rows),
                positives: formatNumber(forecast.model.test_positives),
              })}</span>
            </div>
            <div className="model-metrics">
              <article>
                <span>{t.rankingQuality}</span>
                <strong>{forecast.model.test_metrics.average_precision === null || forecast.model.test_metrics.average_precision === undefined ? "—" : formatPercent(forecast.model.test_metrics.average_precision, 1)}</strong>
                <small>{t.averagePrecision}</small>
              </article>
              <article>
                <span>{t.alertPrecision}</span>
                <strong>{forecast.model.test_metrics.precision === null || forecast.model.test_metrics.precision === undefined ? "—" : formatPercent(forecast.model.test_metrics.precision, 1)}</strong>
                <small>{t.modelAlertsSpread}</small>
              </article>
              <article>
                <span>{t.outcomeRecall}</span>
                <strong>{forecast.model.test_metrics.recall === null || forecast.model.test_metrics.recall === undefined ? "—" : formatPercent(forecast.model.test_metrics.recall, 1)}</strong>
                <small>{t.spreadOutcomesFound}</small>
              </article>
              <article>
                <span>{t.falseAlertsDay}</span>
                <strong>{forecast.model.test_metrics.false_alerts_per_day === null || forecast.model.test_metrics.false_alerts_per_day === undefined ? "—" : formatDecimal(forecast.model.test_metrics.false_alerts_per_day)}</strong>
                <small>{t.observedHoldout}</small>
              </article>
            </div>
          </section>
        ) : (
          <div className="model-unavailable">
            <strong>{t.benchmarkPending}</strong>
            <span>{t.benchmarkAfterRefresh}</span>
          </div>
        )}

        <div className="forecast-workbench">
          <div className="pending-forecast-list">
            <div className="forecast-subheading">
              <strong>{t.openForecastClocks}</strong>
              <span>{t.futureHidden}</span>
            </div>
            {forecast.pending_predictions.length > 0 ? (
              forecast.pending_predictions.map((prediction) => {
                const hoursObserved = Math.max(
                  0,
                  forecast.target.horizon_hours - prediction.hours_remaining,
                );
                const modelPrediction = modelPredictions.get(
                  `${prediction.region_code}|${prediction.window_start}`,
                );
                return (
                  <article className="pending-forecast" key={`${prediction.region_code}|${prediction.window_start}`}>
                    <div className="pending-forecast-title">
                      <div>
                        <span>{prediction.region_code}</span>
                        <strong>{formatWindow(prediction.window_start, localeTag)}</strong>
                      </div>
                      <b>{formatMessage(t.hoursRemaining, { count: formatNumber(prediction.hours_remaining) })}</b>
                    </div>
                    <dl>
                      <div><dt>{t.atDetection}</dt><dd>{formatMessage(prediction.stories_at_detection === 1 ? t.storyOne : t.storyMany, { count: formatNumber(prediction.stories_at_detection) })}</dd></div>
                      <div><dt>{t.sourceDiversity}</dt><dd>{formatMessage(prediction.domains_at_detection === 1 ? t.domainOne : t.domainMany, { count: formatNumber(prediction.domains_at_detection) })}</dd></div>
                      <div><dt>{t.outcomeCloses}</dt><dd>{formatWindow(prediction.matures_at, localeTag)}</dd></div>
                    </dl>
                    {modelPrediction ? (
                      <div className="pending-model-score">
                        <span>{t.modelScore}</span>
                        <strong>{formatDecimal(modelPrediction.model_score * 100)} / 100</strong>
                        <small>
                          {modelPrediction.clears_alert_threshold
                            ? t.clearsThreshold
                            : forecast.model.decision_threshold === null
                              ? t.doesNotClearThreshold
                              : formatMessage(t.belowThreshold, { threshold: formatDecimal(forecast.model.decision_threshold * 100, 2) })}
                        </small>
                        <em>{t.rankingNotProbability}</em>
                      </div>
                    ) : null}
                    <span
                      aria-label={formatMessage(t.outcomeHoursObserved, {
                        observed: formatNumber(hoursObserved),
                        total: formatNumber(forecast.target.horizon_hours),
                      })}
                      aria-valuemax={forecast.target.horizon_hours}
                      aria-valuemin={0}
                      aria-valuenow={hoursObserved}
                      className="forecast-clock"
                      role="progressbar"
                    >
                      <i style={{ width: `${(hoursObserved / forecast.target.horizon_hours) * 100}%` }} />
                    </span>
                  </article>
                );
              })
            ) : (
              <div className="forecast-empty">{t.noCandidateForecasts}</div>
            )}
          </div>

          <aside className="evaluation-gate">
            <span>{t.evaluationGate}</span>
            {forecast.evaluation_ready_windows === 0 ? (
              <>
                <strong>{t.waitingByDesign}</strong>
                <p>{t.waitingExplanation}</p>
              </>
            ) : (
              <>
                <strong>{formatMessage(t.windowsReady, { count: formatNumber(forecast.evaluation_ready_windows) })}</strong>
                <p>{formatMessage(t.precisionRecall, {
                  precision: forecast.precision === null ? "—" : formatPercent(forecast.precision),
                  recall: forecast.recall === null ? "—" : formatPercent(forecast.recall),
                })}</p>
              </>
            )}
            <dl>
              <div><dt>{t.predictionTime}</dt><dd>{t.hourZeroFeatures}</dd></div>
              <div><dt>{t.outcomeWindow}</dt><dd>{formatMessage(t.hoursRange, { hours: formatNumber(forecast.target.horizon_hours) })}</dd></div>
              <div><dt>{t.successThreshold}</dt><dd>{formatMessage(forecast.target.domain_threshold === 1 ? t.domainOne : t.domainMany, { count: formatNumber(forecast.target.domain_threshold) })}</dd></div>
            </dl>
          </aside>
        </div>
      </section>

      <section className="content-grid" id="signals">
        <article className="surface evidence-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{t.latestEligibleHour}</p>
              <h2>{t.enoughEvidence}</h2>
            </div>
            <span className={hasCandidates ? "status-badge alert" : "status-badge"}>
              {hasCandidates
                ? formatMessage(snapshot.candidates === 1 ? t.candidateOne : t.candidateMany, { count: formatNumber(snapshot.candidates) })
                : formatMessage(t.normalCount, { count: formatNumber(statusCounts.normal) })}
            </span>
          </div>

          <div className="table-wrap">
            <table className="signal-table">
              <thead>
                <tr>
                  <th scope="col">{t.region}</th>
                  <th scope="col">{t.stories}</th>
                  <th scope="col">{t.domains}</th>
                  <th scope="col">{t.baseline}</th>
                  <th scope="col">{t.score}</th>
                  <th scope="col">{t.signalStatus}</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((signal) => {
                  const localizedStatus = statusRows.find((row) => row.key === signal.status)?.label
                    ?? t.normalStatus;
                  return (
                    <tr key={signalID(signal)}>
                      <td data-label={t.region}><strong>{signal.region}</strong><small>{signal.code}</small></td>
                      <td data-label={t.stories}>{formatNumber(signal.stories)}</td>
                      <td data-label={t.domains}>{formatNumber(signal.domains)}</td>
                      <td data-label={t.baseline}>{signal.baseline === null ? "—" : formatDecimal(signal.baseline)}</td>
                      <td className="mono" data-label={t.score}>{formatSignalScore(signal, t.zeroBaselineJump)}</td>
                      <td data-label={t.signalStatus}>
                        <span className={signal.status === "candidate_anomaly" ? "alert-pill" : "normal-pill"}>
                          <i />{localizedStatus}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="table-note">{t.normalMeaning}</p>
        </article>

        <aside className="surface readiness-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{t.scoringReadiness}</p>
              <h2>{t.everyRow}</h2>
            </div>
          </div>
          <div className="status-list">
            {statusRows.map((row) => {
              const count = statusCounts[row.key];
              return (
                <div key={row.key}>
                  <span className="status-name"><i className={`dot ${row.tone}`} />{row.label}</span>
                  <strong>{formatNumber(count)}</strong>
                  <span className="status-bar"><i style={{ width: barWidth(count) }} /></span>
                </div>
              );
            })}
          </div>
          <div className="next-window">
            <span>{t.humanReviewActive}</span>
            <strong>{t.labelCandidates}</strong>
            <p>{t.reviewFoundation}</p>
          </div>
        </aside>
      </section>

      <section className="method-strip" id="method" aria-label={t.howItWorksAria}>
        <div>
          <p className="eyebrow">{t.howResultMade}</p>
          <h2>{t.evidenceInDecisionsOut}</h2>
        </div>
        <ol>
          <li><span>01</span><strong>{t.collect}</strong><small>{t.collectDetail}</small></li>
          <li><span>02</span><strong>{t.clean}</strong><small>{t.cleanDetail}</small></li>
          <li><span>03</span><strong>{t.group}</strong><small>{t.groupDetail}</small></li>
          <li><span>04</span><strong>{t.compare}</strong><small>{t.compareDetail}</small></li>
          <li><span>05</span><strong>{t.gate}</strong><small>{t.gateDetail}</small></li>
        </ol>
      </section>

      <footer>
        <p><strong>CrisisPulse</strong> {t.footerWarning}</p>
        <p>{t.footerCost}</p>
      </footer>
    </main>
  );
}
