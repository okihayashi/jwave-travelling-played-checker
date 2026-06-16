const data = window.TWM_DATA || { tracks: [], episodes: [] };
const queryInput = document.querySelector("#query");
const clearButton = document.querySelector("#clear");
const stats = document.querySelector("#stats");
const answer = document.querySelector("#answer");
const results = document.querySelector("#results");

const collator = new Intl.Collator(undefined, { sensitivity: "base", usage: "search" });

function normalize(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[’‘`´]/g, "'")
    .replace(/[‐-‒–—―]/g, "-")
    .replace(/[^\p{Letter}\p{Number}]+/gu, " ")
    .trim();
}

function withoutLeadingArticle(value) {
  return value.replace(/^(the|a|an)\s+/i, "");
}

function searchVariants(value) {
  const normalized = normalize(value);
  const articleless = withoutLeadingArticle(normalized);
  return [...new Set([normalized, articleless].filter(Boolean))];
}

function searchText(track) {
  return normalize(`${track.title} ${track.artist} ${track.raw_title}`);
}

function exactSongMatch(track, query) {
  const queryVariants = searchVariants(query);
  return [...searchVariants(track.title), ...searchVariants(track.raw_title)].some((value) =>
    queryVariants.some((variant) => collator.compare(value, variant) === 0)
  );
}

function byDateThenTrack(a, b) {
  return a.episode_date.localeCompare(b.episode_date) || a.track_number - b.track_number;
}

function highlight(value, query) {
  const text = String(value || "");
  const q = query.trim();
  if (!q || q.length < 2) return escapeHtml(text);

  const lower = text.toLowerCase();
  const index = lower.indexOf(q.toLowerCase());
  if (index < 0) return escapeHtml(text);

  return `${escapeHtml(text.slice(0, index))}<mark>${escapeHtml(text.slice(index, index + q.length))}</mark>${escapeHtml(text.slice(index + q.length))}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatTheme(theme) {
  const cleaned = String(theme || "").replace(/★/g, "").replace(/\s+/g, " ").trim();
  return cleaned.length > 140 ? `${cleaned.slice(0, 140)}...` : cleaned;
}

function renderStats() {
  const first = data.episodes[0]?.date?.replaceAll(".", "-") || "";
  const last = data.episodes.at(-1)?.date?.replaceAll(".", "-") || "";
  const appleMatches = data.apple_music?.matched_track_count;
  const appleLine = Number.isFinite(appleMatches) ? `<br>${appleMatches.toLocaleString()} Apple Music links` : "";
  stats.innerHTML = `${data.track_count.toLocaleString()} tracks<br>${data.episode_count.toLocaleString()} episodes<br>${first} to ${last}${appleLine}`;
}

function renderAnswer(query, matches) {
  if (!query) {
    answer.innerHTML = `
      <div>
        <strong>Type a song title or artist.</strong>
        <span>The checker searches the archived MUSIC STREAM data.</span>
      </div>
      <div class="badge">Ready</div>
    `;
    return;
  }

  if (!matches.length) {
    answer.innerHTML = `
      <div>
        <strong>No match found.</strong>
        <span>${escapeHtml(query)} does not appear in the current archive data.</span>
      </div>
      <div class="badge">Likely OK</div>
    `;
    return;
  }

  const first = matches[0];
  const exact = matches.some((track) => exactSongMatch(track, query));
  answer.innerHTML = `
    <div>
      <strong>${matches.length === 1 ? "Already played once." : `Found ${matches.length} possible matches.`}</strong>
      <span>Earliest match: ${escapeHtml(first.episode_date.replaceAll(".", "-"))}, track ${first.track_number}.</span>
    </div>
    <div class="badge">${exact ? "Song Match" : "Check Matches"}</div>
  `;
}

function renderResults(query, matches) {
  if (!query) {
    const latest = [...data.tracks].sort(byDateThenTrack).slice(-12).reverse();
    results.innerHTML = latest.map((track) => renderCard(track, query)).join("");
    return;
  }

  results.innerHTML = matches.slice(0, 80).map((track) => renderCard(track, query)).join("");
}

function renderCard(track, query) {
  const isExact = query && exactSongMatch(track, query);
  const theme = formatTheme(track.episode_theme);
  const appleLink = track.apple_music_url
    ? `<a href="${escapeHtml(track.apple_music_url)}" target="_blank" rel="noreferrer" title="${escapeHtml(formatAppleTitle(track))}">Apple Music</a>`
    : "";
  return `
    <article class="card ${isExact ? "match-song" : ""}">
      <div class="track-line">
        <div class="track-number">${track.track_number}</div>
        <div>
          <div class="song">${highlight(track.title, query)}</div>
          <div class="artist">${highlight(track.artist || "Unknown artist", query)}</div>
        </div>
      </div>
      <div class="meta">
        <span>${escapeHtml(track.episode_date.replaceAll(".", "-"))}</span>
        <a href="${escapeHtml(track.episode_url)}" target="_blank" rel="noreferrer">episode</a>
        ${appleLink}
      </div>
      ${theme ? `<div class="theme">${escapeHtml(theme)}</div>` : ""}
    </article>
  `;
}

function formatAppleTitle(track) {
  if (!track.apple_music_track_name) return "Open in Apple Music";
  const album = track.apple_music_album_name ? `, ${track.apple_music_album_name}` : "";
  return `${track.apple_music_track_name} - ${track.apple_music_artist_name}${album}`;
}

function scoreTrack(track, query) {
  const normalizedQuery = normalize(query);
  const queryVariants = searchVariants(query);
  const text = searchText(track);
  const textVariants = searchVariants(text);
  const titleVariants = searchVariants(track.title);
  const artistVariants = searchVariants(track.artist);
  const rawVariants = searchVariants(track.raw_title);

  const sameAsQuery = (values) => values.some((value) => queryVariants.includes(value));
  const includesQuery = (values) =>
    values.some((value) => queryVariants.some((variant) => value.includes(variant)));
  const hasAllWords = queryVariants.some((variant) => {
    const words = variant.split(/\s+/).filter(Boolean);
    return words.length > 0 && words.every((word) => textVariants.some((value) => value.includes(word)));
  });

  if (!normalizedQuery) return 0;
  if (sameAsQuery(titleVariants) || sameAsQuery(rawVariants)) return 100;
  if (sameAsQuery(artistVariants)) return 90;
  if (includesQuery(titleVariants)) return 80;
  if (includesQuery(artistVariants)) return 70;
  if (includesQuery(rawVariants)) return 65;
  if (hasAllWords) return 45;
  return 0;
}

function runSearch() {
  const query = queryInput.value.trim();
  const matches = data.tracks
    .map((track) => ({ track, score: scoreTrack(track, query) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || byDateThenTrack(a.track, b.track))
    .map((item) => item.track);

  const chronologicalMatches = [...matches].sort(byDateThenTrack);
  renderAnswer(query, chronologicalMatches);
  renderResults(query, matches);
}

clearButton.addEventListener("click", () => {
  queryInput.value = "";
  queryInput.focus();
  runSearch();
});

queryInput.addEventListener("input", runSearch);

renderStats();
runSearch();
