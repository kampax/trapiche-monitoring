# ==============================================================================
# Analisis Sentinel-2 -- Efecto de tratamientos de restauracion sobre indices
# de vegetacion (NDVI, EVI, LSWI, SAVI) en el sitio Trapiche
#
# Estructura del script:
#   1. Librerias
#   2. Carga y limpieza de datos
#   3. Control de calidad de escenas (cobertura minima + deteccion de artefactos)
#   4. Configuracion grafica compartida (tema, paleta, helper de guardado)
#   5. Resumen por escena/tratamiento/epoca
#   6. Pipeline de analisis por indice (modelo LMM, ANOVA, post-hoc emmeans/cld,
#      y los 3 graficos estandar), aplicado de forma identica a NDVI, EVI, LSWI y SAVI
#   7. Exportacion de tablas para material suplementario
#
# Nota sobre NDWI: se excluye del analisis. Es un indice orientado a contenido
# de agua/humedad de superficie, no a vigor de vegetacion, y no forma parte de
# las preguntas de este estudio (efecto de restauracion sobre la vegetacion).
# ==============================================================================

# 1. Librerias -----------------------------------------------------------------

library(tidyverse)
library(lme4)
library(lmerTest) # sobrescribe lmer() de lme4 para agregar p-valores (Satterthwaite) a summary()
library(emmeans)
library(multcomp)  # provee la funcion generica cld() que usa emmeans para las letras de significancia
library(lubridate)
library(patchwork)

# 2. Carga y limpieza de datos --------------------------------------------------

# El script vive en scripts/3-analysis scripts/, dos niveles bajo la raiz del
# proyecto (Analisis/); se sube tres niveles desde la ruta del script (archivo
# -> "3-analysis scripts" -> "scripts" -> raiz) para ubicar data/ de forma
# robusta sin importar desde donde se invoque Rscript.
project_root <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) == 1) {
    script_path <- normalizePath(sub("^--file=", "", file_arg))
    return(dirname(dirname(dirname(script_path))))
  }
  wd <- normalizePath(getwd())
  if (basename(dirname(wd)) == "scripts") return(dirname(dirname(wd)))
  if (basename(wd) == "scripts") return(dirname(wd))
  wd
}

root_dir <- project_root()
input_file <- file.path(root_dir, "data", "datos_trapiche_sentinel.csv")

df_raw <- read_csv(input_file)
# df_raw <- read_csv(file.path(root_dir, "data", "datos_trapiche_sentinel_limpios.csv"))

# Filtrar desde julio 2024, quitar valores fuera de rango y colapsar por pixel-fecha-tratamiento
df <- df_raw %>%
  mutate(
    Point_ID = as.integer(Point_ID),
    Year = as.integer(Year),
    Date = as.Date(Date),
    NDVI = as.numeric(NDVI),
    EVI = as.numeric(EVI),
    SAVI = as.numeric(SAVI),
    LSWI = as.numeric(LSWI),
    Snow = as.numeric(Snow)
  ) %>%
  filter(Date >= as.Date("2024-07-01")) %>%
  filter(between(EVI, -1, 1), between(NDVI, -1, 1)) %>%
  filter(Snow == 0) %>%
  group_by(Point_ID, Date, tratamiento) %>%
  summarise(
    Year = first(Year),
    across(c(NDVI, EVI, SAVI, LSWI), ~ median(.x, na.rm = TRUE)),
    Snow = max(Snow, na.rm = TRUE),
    .groups = "drop"
  )

# 3. Control de calidad de escenas ----------------------------------------------

# 3a. Cobertura minima: exigir >= 80% de los pixeles validos en las 4 zonas de tratamiento
scene_totals <- df %>%
  group_by(tratamiento) %>%
  summarise(total_pixels = n_distinct(Point_ID), .groups = "drop")

scene_coverage <- df %>%
  group_by(Date, tratamiento) %>%
  summarise(valid_pixels = n_distinct(Point_ID), .groups = "drop") %>%
  left_join(scene_totals, by = "tratamiento") %>%
  mutate(coverage = valid_pixels / total_pixels)

valid_scene_dates <- scene_coverage %>%
  group_by(Date) %>%
  summarise(
    min_coverage = min(coverage, na.rm = TRUE),
    n_sectors = n_distinct(tratamiento),
    .groups = "drop"
  ) %>%
  filter(n_sectors == 4, min_coverage >= 0.8) %>%
  pull(Date)

df <- df %>%
  filter(Date %in% valid_scene_dates)

# 3b. Deteccion de artefactos residuales: escenas cuyo EVI cae muy por debajo de
# la mediana movil local (nubes/sombras no capturadas por la mascara de nieve)
evi_trend_checks <- df %>%
  group_by(Date, tratamiento) %>%
  summarise(mean_EVI = mean(EVI, na.rm = TRUE), .groups = "drop") %>%
  arrange(tratamiento, Date) %>%
  group_by(tratamiento) %>%
  mutate(
    local_median_7 = runmed(mean_EVI, k = 7, endrule = "median"),
    residual = mean_EVI - local_median_7
  ) %>%
  ungroup()

bad_dates <- evi_trend_checks %>%
  group_by(Date) %>%
  summarise(min_residual = min(residual, na.rm = TRUE), .groups = "drop") %>%
  filter(min_residual < -0.045) %>%
  pull(Date)

df <- df %>%
  filter(!Date %in% bad_dates)

message("Filtrado fisico y colapso por pixel-fecha: ", nrow(df_raw), " -> ", nrow(df), " filas finales")
message("Escenas validas tras cobertura minima: ", length(valid_scene_dates))
message("Escenas removidas por artefactos residuales: ", length(bad_dates))

# 4. Configuracion grafica compartida -------------------------------------------

treatment_colors <- c(
  "control 1" = "#1B4D3E",
  "control 2" = "#4D8659",
  "sector no restaurado" = "#A62C2C",
  "sector restaurado" = "#D4A574"
)

output_dir <- file.path(root_dir, "figures", "sentinel2")
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

table_dir <- file.path(root_dir, "tables", "sentinel2")
if (!dir.exists(table_dir)) {
  dir.create(table_dir, recursive = TRUE)
}

base_theme <- theme_classic(base_size = 12, base_family = "serif") +
  theme(
    plot.title = element_text(face = "bold", size = 15),
    plot.subtitle = element_text(size = 11, margin = margin(b = 10)),
    axis.title = element_text(size = 16),
    axis.text = element_text(size = 14),
    axis.text.x = element_text(angle = 45, hjust = 1, size = 14),
    legend.position = "top",
    legend.title = element_text(face = "bold", size = 13),
    legend.text = element_text(size = 12),
    panel.grid.major.y = element_line(color = "grey85", linewidth = 0.3),
    panel.grid.minor.y = element_blank()
  )

boxplot_epoch_theme <- base_theme +
  theme(
    strip.background = element_rect(fill = "grey96", color = "grey30"),
    strip.text = element_text(size = 16, face = "bold"),
    axis.text.x = element_text(size = 13, angle = 45, hjust = 1),
    axis.title.x = element_text(size = 16),
    axis.title.y = element_text(size = 16)
  )

save_plot <- function(plot, filename, width = 11, height = 6.5) {
  ggsave(
    filename = file.path(output_dir, filename),
    plot = plot,
    width = width,
    height = height,
    dpi = 320,
    bg = "white"
  )
}

season_background <- tibble(
  epoca = factor(c("humeda", "seca"), levels = c("humeda", "seca")),
  xmin = c(0.5, 1.5),
  xmax = c(1.5, 2.5),
  ymin = -Inf,
  ymax = Inf,
  fill = c("#6AA84F", "#FFD966")
)

# 5. Resumen por escena/tratamiento/epoca ----------------------------------------

# Promedio por escena de cada tratamiento
resumen <- df %>%
  group_by(Date, tratamiento) %>%
  summarise(
    mean_NDVI = mean(NDVI, na.rm = TRUE),
    mean_EVI = mean(EVI, na.rm = TRUE),
    mean_LSWI = mean(LSWI, na.rm = TRUE),
    mean_SAVI = mean(SAVI, na.rm = TRUE),
    .groups = "drop"
  )

# Epoca humeda: noviembre-abril; epoca seca: mayo-octubre
resumen2 <- resumen %>%
  mutate(epoca = ifelse(month(Date) %in% c(11, 12, 1, 2, 3, 4), "humeda", "seca"))

# 6. Pipeline de analisis por indice ---------------------------------------------
#
# Para cada indice (NDVI, EVI, LSWI, SAVI) se ajusta el mismo modelo mixto
# (tratamiento * epoca, con Date como efecto aleatorio para no pseudo-replicar
# entre pixeles de una misma escena), se prueba la interaccion con ANOVA tipo III
# (Satterthwaite), se estiman las medias marginales (emmeans) condicionadas a la
# epoca -- es decir, los tratamientos se comparan entre si DENTRO de cada epoca,
# que es lo que despues se muestra en paneles separados -- y se generan los
# mismos 3 graficos: evolucion de la media por epoca, boxplot por tratamiento x
# epoca, y medias marginales estimadas +/- IC 95% con letras de significancia
# (Tukey).

analyze_index <- function(data, index) {
  formula_mod <- as.formula(paste0("mean_", index, " ~ tratamiento * epoca + (1 | Date)"))
  modelo <- lmer(formula_mod, data = data)

  cat("\n============================================================\n")
  cat("Modelo LMM:", index, "~ tratamiento * epoca + (1 | Date)\n")
  cat("============================================================\n")
  print(summary(modelo))

  anova_tab <- anova(modelo) # test global de tratamiento, epoca y su interaccion
  cat("\n-- ANOVA (Satterthwaite) --\n")
  print(anova_tab)

  ci <- confint(profile(modelo))
  cat("\n-- IC 95% por perfil de verosimilitud --\n")
  print(ci)

  # Comparaciones post-hoc de tratamiento DENTRO de cada epoca (medias marginales estimadas)
  emm <- emmeans(modelo, ~ tratamiento | epoca)
  pw <- pairs(emm, adjust = "tukey")
  cat("\n-- Comparaciones pareadas (Tukey), dentro de cada epoca --\n")
  print(pw)

  emm_cld <- cld(emm, adjust = "tukey", Letters = letters) # letras (a, b, ...) en vez de codigos numericos concatenados
  cat("\n-- Letras de significancia (CLD) --\n")
  print(emm_cld)

  # -- Graficos --------------------------------------------------------------

  data_idx <- data %>% mutate(y = .data[[paste0("mean_", index)]])
  y_lab <- paste(index, "medio")

  p_line <- ggplot(data_idx, aes(epoca, y, colour = tratamiento, group = tratamiento)) +
    geom_rect(
      data = season_background,
      inherit.aes = FALSE,
      aes(xmin = xmin, xmax = xmax, ymin = ymin, ymax = ymax, fill = fill),
      alpha = 0.16,
      color = NA
    ) +
    stat_summary(fun = mean, geom = "line", linewidth = 1.3) +
    stat_summary(fun = mean, geom = "point", size = 3) +
    scale_color_manual(values = treatment_colors) +
    scale_fill_identity(guide = "none") +
    scale_x_discrete(labels = c("humeda" = "Humeda", "seca" = "Seca")) +
    labs(x = "Epoca", y = y_lab, colour = "Tratamiento") +
    base_theme +
    theme(axis.text.x = element_text(size = 18, face = "bold"))

  save_plot(p_line, paste0(tolower(index), "_media_por_epoca_tratamiento.png"))

  p_box <- ggplot(data_idx, aes(tratamiento, y, fill = tratamiento)) +
    geom_rect(data = filter(season_background, epoca == "humeda"), inherit.aes = FALSE,
              xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf, fill = "#6AA84F", alpha = 0.12) +
    geom_rect(data = filter(season_background, epoca == "seca"), inherit.aes = FALSE,
              xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf, fill = "#FFD966", alpha = 0.12) +
    geom_boxplot(width = 0.7, outlier.size = 1.8, linewidth = 0.35) +
    facet_wrap(~epoca, nrow = 1) +
    scale_fill_manual(values = treatment_colors) +
    labs(x = "Tratamiento", y = y_lab, fill = "Tratamiento") +
    boxplot_epoch_theme

  save_plot(p_box, paste0(tolower(index), "_por_tratamiento_epoca.png"), width = 11.5, height = 6.5)

  emm_plot_data <- as.data.frame(emm_cld) %>%
    mutate(.group = str_trim(.group))

  p_emm <- ggplot(emm_plot_data, aes(x = tratamiento, y = emmean, colour = tratamiento)) +
    geom_rect(data = filter(season_background, epoca == "humeda"), inherit.aes = FALSE,
              xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf, fill = "#6AA84F", alpha = 0.12) +
    geom_rect(data = filter(season_background, epoca == "seca"), inherit.aes = FALSE,
              xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf, fill = "#FFD966", alpha = 0.12) +
    geom_pointrange(aes(ymin = lower.CL, ymax = upper.CL), linewidth = 0.9, size = 0.7) +
    geom_text(aes(y = upper.CL, label = .group), vjust = -0.8, size = 5, fontface = "bold", show.legend = FALSE) +
    facet_wrap(~epoca, nrow = 1) +
    scale_color_manual(values = treatment_colors) +
    scale_y_continuous(expand = expansion(mult = c(0.06, 0.16))) +
    labs(
      x = "Tratamiento",
      y = paste(index, "medio estimado (emmeans, IC 95%)"),
      colour = "Tratamiento",
      caption = "Letras distintas = diferencia significativa entre tratamientos dentro de la misma epoca (Tukey, gl. Satterthwaite)"
    ) +
    boxplot_epoch_theme

  save_plot(p_emm, paste0(tolower(index), "_emmeans_cld_por_tratamiento_epoca.png"), width = 11.5, height = 6.5)

  # -- Tablas para exportar (material suplementario) --------------------------

  coefs <- as.data.frame(coef(summary(modelo))) %>%
    rownames_to_column("term")
  ci_fixed <- as.data.frame(ci) %>%
    rownames_to_column("term") %>%
    filter(term %in% coefs$term) %>%
    rename(ci_low = `2.5 %`, ci_high = `97.5 %`)
  coefs <- left_join(coefs, ci_fixed, by = "term") %>%
    mutate(indice = index, .before = 1)

  anova_df <- as.data.frame(anova_tab) %>%
    rownames_to_column("term") %>%
    mutate(indice = index, .before = 1)

  cld_df <- emm_plot_data %>%
    mutate(indice = index, .before = 1)

  pairwise_df <- as.data.frame(pw) %>%
    mutate(indice = index, .before = 1)

  list(
    modelo = modelo,
    coefs = coefs,
    anova = anova_df,
    cld = cld_df,
    pairwise = pairwise_df,
    plots = list(line = p_line, box = p_box, emm = p_emm)
  )
}

resultados <- map(c("NDVI", "EVI", "LSWI", "SAVI"), ~ analyze_index(resumen2, .x)) %>%
  set_names(c("NDVI", "EVI", "LSWI", "SAVI"))

# 7. Exportacion de tablas para material suplementario ----------------------------

coefs_all <- map_dfr(resultados, "coefs")
anova_all <- map_dfr(resultados, "anova")
cld_all <- map_dfr(resultados, "cld")
pairwise_all <- map_dfr(resultados, "pairwise")

descriptivos <- resumen2 %>%
  pivot_longer(starts_with("mean_"), names_to = "indice", names_prefix = "mean_", values_to = "valor") %>%
  group_by(indice, tratamiento, epoca) %>%
  summarise(
    n_escenas = n_distinct(Date),
    media = mean(valor, na.rm = TRUE),
    sd = sd(valor, na.rm = TRUE),
    .groups = "drop"
  )

qc_summary <- tibble(
  filas_crudas = nrow(df_raw),
  filas_finales = nrow(df),
  escenas_validas_cobertura = length(valid_scene_dates),
  escenas_removidas_artefactos = length(bad_dates)
)

write_csv(coefs_all, file.path(table_dir, "coeficientes_modelo_por_indice.csv"))
write_csv(anova_all, file.path(table_dir, "anova_por_indice.csv"))
write_csv(cld_all, file.path(table_dir, "emmeans_cld_por_indice.csv"))
write_csv(pairwise_all, file.path(table_dir, "pairwise_por_indice.csv"))
write_csv(descriptivos, file.path(table_dir, "descriptivos_indice_tratamiento_epoca.csv"))
write_csv(qc_summary, file.path(table_dir, "control_calidad_escenas.csv"))

# 8. Figuras adicionales para el manuscrito ---------------------------------------

# 8a. Figura compuesta NDVI + EVI (alternativa de "Figura 1" del cuerpo del
# articulo): combina las medias marginales +/- IC 95% con letras de
# significancia de NDVI y EVI en un solo panel de 2 filas, reutilizando los
# graficos ya generados en analyze_index() para no duplicar codigo de ploteo.
p_fig1_ndvi_evi <- (resultados$NDVI$plots$emm / resultados$EVI$plots$emm) +
  plot_layout(guides = "collect") &
  theme(legend.position = "top")

p_fig1_ndvi_evi <- p_fig1_ndvi_evi +
  plot_annotation(tag_levels = "A")

save_plot(p_fig1_ndvi_evi, "figura1_ndvi_evi_emmeans_cld.png", width = 11, height = 12)

# 8b. Serie temporal continua (NDVI y EVI) a lo largo de todo el periodo
# analizado, con las 111 fechas reales (no agregadas por epoca) -- pensada
# para el material suplementario, como respaldo visual del control de calidad
# de escenas y de la estacionalidad real observada.
dates_epoca <- resumen2 %>%
  distinct(Date, epoca) %>%
  arrange(Date)

rle_epoca <- rle(dates_epoca$epoca)
seg_end_idx <- cumsum(rle_epoca$lengths)
seg_start_idx <- c(1, head(seg_end_idx, -1) + 1)

season_segments <- tibble(
  epoca = rle_epoca$values,
  start_date = dates_epoca$Date[seg_start_idx],
  end_date = dates_epoca$Date[seg_end_idx]
) %>%
  mutate(
    xmin = start_date - 5,
    xmax = end_date + 5,
    fill = ifelse(epoca == "humeda", "#6AA84F", "#FFD966")
  )

time_series_theme <- base_theme +
  theme(axis.text.x = element_text(angle = 45, hjust = 1, size = 12))

make_time_series_plot <- function(data, index) {
  data_idx <- data %>% mutate(y = .data[[paste0("mean_", index)]])

  ggplot(data_idx, aes(Date, y, colour = tratamiento, group = tratamiento)) +
    geom_rect(
      data = season_segments,
      inherit.aes = FALSE,
      aes(xmin = xmin, xmax = xmax, ymin = -Inf, ymax = Inf, fill = fill),
      alpha = 0.14,
      color = NA
    ) +
    geom_line(linewidth = 0.6, alpha = 0.85) +
    geom_point(size = 1.6) +
    scale_color_manual(values = treatment_colors) +
    scale_fill_identity(guide = "none") +
    scale_x_date(date_breaks = "2 months", date_labels = "%b %Y") +
    labs(x = "Fecha de escena", y = paste(index, "medio por escena"), colour = "Tratamiento") +
    time_series_theme
}

p_ts_ndvi <- make_time_series_plot(resumen2, "NDVI")
p_ts_evi <- make_time_series_plot(resumen2, "EVI")

p_ts_ndvi_evi <- (p_ts_ndvi / p_ts_evi) +
  plot_layout(guides = "collect") &
  theme(legend.position = "top")

p_ts_ndvi_evi <- p_ts_ndvi_evi +
  plot_annotation(tag_levels = "A")

save_plot(p_ts_ndvi_evi, "serie_temporal_ndvi_evi.png", width = 13, height = 11)

message("Tablas exportadas a ", table_dir)
message("Figuras exportadas a ", output_dir)
