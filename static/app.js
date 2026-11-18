const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");

const SAMPLE = `Senior AI Engineer wanted to lead our agent platform. You will
design the tool calling layer, own the evaluation harness, and set technical
direction for a team of four. We want someone who has shipped LLM products to
real users. Python and TypeScript. Experience with LangChain and vector
databases expected. AWS. Eight years overall, at least two with language
models. London, three days a week in the office.`;

async function health(){
  try{
    const h = await (await fetch("/api/health")).json();
    const b = [];
    b.push(`<span class="badge">env: ${esc(h.environment)}</span>`);
    b.push(`<span class="badge">db: ${esc(h.database)}</span>`);
    b.push(`<span class="badge">${h.api_key_configured
      ? "api key set" : "no api key, demo mode"}</span>`);
    $("#badges").innerHTML = b.join("");
    $("#foot").textContent =
      `model ${h.model} · knowledge files: ${h.knowledge_files.join(", ")}`;
    if(h.warning){
      $("#badges").insertAdjacentHTML("afterend",
        `<div class="notice wrap">${esc(h.warning)}</div>`);
    }
  }catch(e){ $("#badges").innerHTML =
    `<span class="badge warn">backend unreachable</span>`; }
}

function drawStages(trace){
  $("#stages").innerHTML = trace.map(t => `
    <div class="stage ${t.ok ? "" : "fail"}">
      <div class="n">${t.stage}</div>
      <div class="sbody">
        <div class="sname">${esc(t.name)}
          <span class="${t.ok ? "pass" : "fail-t"}">${t.ok ? "ok" : "FAILED"}</span>
        </div>
        <div class="sdetail">${esc(t.detail)}</div>
        ${(t.passages && t.passages.length) ? `<table>
          <thead><tr><th>score</th><th>passage</th><th>heading</th></tr></thead>
          <tbody>${t.passages.map(p=>`<tr><td>${p.score}</td>
            <td>${esc(p.id)}</td><td>${esc(p.heading)}</td></tr>`).join("")}
          </tbody></table>` : ""}
      </div>
      <div class="ms">${t.ms} ms</div>
    </div>`).join("");
  $("#pipeline-panel").hidden = false;
}

function drawAnswer(a){
  if(!a){ $("#answer-panel").hidden = true; return; }
  $("#answer").innerHTML = "<dl>" + Object.entries(a).map(([k,v]) =>
    `<dt>${esc(k)}</dt><dd>${esc(Array.isArray(v)? v.join(", ") : v)}</dd>`
  ).join("") + "</dl>";
  $("#answer-panel").hidden = false;
}

async function decode(){
  const advert = $("#advert").value.trim();
  if(!advert){ $("#status").textContent = "paste something first"; return; }
  $("#go").disabled = true; $("#status").textContent = "sending to the backend...";
  try{
    const res = await fetch("/api/decode",{method:"POST",
      headers:{"content-type":"application/json"},
      body:JSON.stringify({advert})});
    const d = await res.json();
    if(d.trace) drawStages(d.trace);
    drawAnswer(d.answer);
    $("#status").textContent = d.ok
      ? `done in ${d.total_ms} ms`
      : `refused: ${d.refusal || d.error || "unknown"}`;
  }catch(e){ $("#status").textContent = "could not reach the backend: " + e.message; }
  finally{ $("#go").disabled = false; }
}

async function loadRecent(){
  $("#store-status").textContent = "loading...";
  try{
    const r = await (await fetch("/api/recent?limit=10")).json();
    if(r.error){ $("#store-status").textContent = r.error; return; }
    $("#store-status").textContent =
      `${r.stats.requests} requests stored in ${r.backend}`;
    $("#recent").innerHTML = r.rows.length ? `<table>
      <thead><tr><th>#</th><th>env</th><th>chars</th><th>ok</th><th>mode</th>
        <th>seniority</th><th>ms</th></tr></thead>
      <tbody>${r.rows.map(x=>`<tr><td>${x.id}</td><td>${esc(x.environment)}</td>
        <td>${x.advert_chars}</td><td>${x.ok ? "yes":"no"}</td>
        <td>${esc(x.mode??"")}</td><td>${esc(x.seniority??"")}</td>
        <td>${x.total_ms}</td></tr>`).join("")}</tbody></table>`
      : "<p class='muted'>Nothing stored yet.</p>";
  }catch(e){ $("#store-status").textContent = e.message; }
}

$("#go").addEventListener("click", decode);
$("#sample").addEventListener("click", () => {
  $("#advert").value = SAMPLE.replace(/\s+/g," ").trim();
});
$("#refresh").addEventListener("click", loadRecent);
health();
