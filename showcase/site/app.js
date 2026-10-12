// AdventureWorks modernization showcase (Phase 8). Plain JS, no build step: data comes from data/*.json, which
// showcase/build.py copies from the repo's single sources of truth (mapping.json, access-patterns.json, results).
(async function () {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const get = async (u, d) => { try { const r = await fetch(u); if (!r.ok) throw r.status; return await r.json(); } catch (e) { return d; } };
  const [cfg, M, AP, RES, LOAD, BUILD] = await Promise.all([
    get('config.json', {}), get('data/mapping.json'), get('data/access-patterns.json'),
    get('data/results.json', {}), get('data/load-stats.json', {}), get('data/build.json', {})]);
  $('#build').textContent = BUILD.commit ? `build ${BUILD.commit} · ${BUILD.built}` : '';
  const fmtN = n => n == null ? '–' : Number(n).toLocaleString('en-US');

  // ---------- tabs ----------
  const tabs = [...document.querySelectorAll('nav button')];
  const rendered = {};
  function show(id) {
    if (!tabs.some(t => t.dataset.tab === id)) id = 'presentation';
    tabs.forEach(t => t.setAttribute('aria-selected', t.dataset.tab === id));
    document.querySelectorAll('main section').forEach(s => s.classList.toggle('on', s.id === id));
    if (!rendered[id]) { rendered[id] = 1; R[id](); }
  }
  tabs.forEach(t => t.onclick = () => { location.hash = t.dataset.tab; });
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));

  const tables = Object.keys(M.tables);
  const sources = M.sources;
  const R = {};

  // ---------- Presentation ----------
  R.presentation = () => {
    const e2e = RES.end_to_end || {}, bl = RES.bulk_load || {}, rc = RES.reconciliation || {};
    const nPat = AP.patterns.length, nDdb = AP.patterns.filter(p => p.scope === 'dynamodb').length;
    const slides = [
      { k: 'The challenge', h: 'A 20-year-old SQL Server shop, modernized without a big-bang cutover',
        b: ['AdventureWorks: 68 business tables, an ASP.NET MVC storefront and an AdventureWorksDW star schema',
            'Goal: serverless, pay-per-request data on Amazon DynamoDB, analytics on Amazon Redshift, everything in Terraform',
            'Constraint: the old app keeps running while the new one goes live: side by side, one-way CDC'] },
      { k: 'Approach', h: 'Access patterns first, then one table per business domain',
        b: [`${nPat} access patterns captured with the business (${nDdb} served by DynamoDB keys, the rest by Redshift)`,
            `${tables.length} domain tables (${tables.join(', ')}), single-table design per domain`,
            'One mapping file (mapping.json) drives the bulk loader, the CDC transform, the Redshift staging views and this site'] },
      { k: 'Migration', h: 'Bulk load + change data capture, provably complete',
        b: ['SQL Server CDC → AWS DMS → Kinesis → Lambda (Debezium locally): idempotent, ordered by log position',
            'Deletes become tombstones; a missing related item is retried, then dead-lettered'],
        kpi: [['Source rows', fmtN(bl.source_rows)], ['DynamoDB items', fmtN(bl.items)], ['Bulk load', bl.seconds ? bl.seconds + ' s' : '–'],
              ['Order → DynamoDB', e2e.demo_order_to_aw_sales_s ? e2e.demo_order_to_aw_sales_s + ' s' : '–'], ['Reconciliation', rc.sources_matching || '–']] },
      { k: 'The new app', h: '.NET 10 shopper app reading and writing DynamoDB directly',
        b: ['Browse, search, cart (7-day TTL), checkout and order history: one request per page',
            'Strongly consistent reads only for login, cart and read-after-checkout; everything else eventually consistent',
            'Chiseled non-root container on ECS Fargate behind an ALB'] },
      { k: 'Analytics', h: 'Zero-ETL to Redshift Serverless rebuilds the familiar star schema',
        b: ['One zero-ETL integration per domain table: no pipelines to run',
            `${Object.keys(M.dw_lineage).filter(k => k.startsWith('Dim')).length} dimensions and ${Object.keys(M.dw_lineage).filter(k => k.startsWith('Fact')).length} facts rebuilt hourly by one stored procedure; finance/survey data carried over statically`,
            'Reconciled against the original AdventureWorksDW2022 in CI; QuickSight dashboards on top'] },
      { k: 'Operations', h: 'Everything as code, cheap to demo, nothing left running',
        b: ['Terraform for every resource; offline plan tests in CI; OIDC-only deploys with a required reviewer',
            'AWS Budgets alert (USD 50/month); one script tears the demo down',
            'Every phase landed as a reviewed pull request with ADRs'] },
    ];
    let i = 0;
    const el = $('#presentation');
    el.innerHTML = `<div class="card slide" id="slide"></div><div class="deck-nav"><button class="b alt" id="prev">◀ Previous</button><div class="dots" id="dots"></div><button class="b" id="next">Next ▶</button></div>`;
    const draw = () => {
      const s = slides[i];
      $('#slide').innerHTML = `<div class="kick">${i + 1} / ${slides.length} · ${esc(s.k)}</div><h3>${esc(s.h)}</h3><ul>${s.b.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` +
        (s.kpi ? `<div class="kpis">${s.kpi.map(([a, b]) => `<div class="kpi">${esc(a)}<b>${esc(b)}</b></div>`).join('')}</div>` : '');
      $('#dots').innerHTML = slides.map((_, j) => `<span class="${j === i ? 'on' : ''}" data-i="${j}"></span>`).join('');
    };
    $('#prev').onclick = () => { i = (i + slides.length - 1) % slides.length; draw(); };
    $('#next').onclick = () => { i = (i + 1) % slides.length; draw(); };
    $('#dots').onclick = e => { if (e.target.dataset.i) { i = +e.target.dataset.i; draw(); } };
    document.addEventListener('keydown', e => { if (!$('#presentation').classList.contains('on')) return; if (e.key === 'ArrowRight') $('#next').click(); if (e.key === 'ArrowLeft') $('#prev').click(); });
    draw();
  };

  // ---------- Architecture ----------
  const ARCH = {
    before: {
      lanes: [['Users', 20], ['Application', 200], ['Data', 400], ['Reporting', 600]],
      nodes: [
        ['shopper', 'Shopper / staff', 'browser', 40, 60, 'u'],
        ['oldapp', 'AdventureWorks.Web', 'ASP.NET MVC (.NET Fw) on IIS', 220, 60, 'old'],
        ['sql', 'SQL Server', 'AdventureWorks OLTP · 68 tables', 420, 60, 'old'],
        ['etl', 'Nightly ETL', 'SSIS-style jobs', 420, 200, 'old'],
        ['dw', 'AdventureWorksDW', 'star schema on SQL Server', 620, 200, 'old'],
        ['rep', 'Reports', 'SSRS / Excel', 620, 60, 'old']],
      edges: [['shopper', 'oldapp'], ['oldapp', 'sql'], ['sql', 'etl'], ['etl', 'dw'], ['dw', 'rep']],
    },
    after: {
      lanes: [['Users', 20], ['Apps (ECS Fargate + ALB)', 200], ['Change data capture', 400], ['Operational data', 600], ['Analytics', 800]],
      nodes: [
        ['shopper', 'Shopper', 'browser', 40, 60, 'u'],
        ['showcase', 'Showcase site', 'S3 + CloudFront', 40, 230, 'new'],
        ['newapp', '.NET 10 shopper app', 'Fargate, task role', 220, 60, 'new'],
        ['oldapp2', 'Original app (side by side)', 'Fargate, on SQL Server', 220, 230, 'old'],
        ['rds', 'RDS SQL Server SE', 'CDC on 68 tables', 420, 230, 'old'],
        ['dms', 'AWS DMS', 'full images, CDC start time', 420, 330, 'new'],
        ['kin', 'Kinesis Data Streams', 'ordered by key', 420, 430, 'new'],
        ['lambda', 'CDC Lambda (awcdc)', 'mapping-driven transform', 620, 430, 'new'],
        ['ddb', 'DynamoDB × 7 domain tables', tables.join(' · ').replace(/aw-/g, ''), 620, 60, 'new'],
        ['zetl', 'Zero-ETL integrations', 'one per table', 820, 60, 'dw'],
        ['rs', 'Redshift Serverless', 'stg MVs → star schema hourly', 820, 200, 'dw'],
        ['qs', 'QuickSight', 'dashboards (optional)', 820, 330, 'dw']],
      edges: [['shopper', 'newapp'], ['shopper', 'oldapp2'], ['newapp', 'ddb'], ['oldapp2', 'rds'], ['rds', 'dms'], ['dms', 'kin'], ['kin', 'lambda'], ['lambda', 'ddb'], ['ddb', 'zetl'], ['zetl', 'rs'], ['rs', 'qs']],
    },
  };
  const DETAILS = {
    shopper: ['People using the store.', ''],
    oldapp: ['The archived Azure-Samples ASP.NET MVC app: every page is a SQL query against the normalised schema.', 'Controllers/, Views/'],
    sql: ['One large relational database shared by every domain: 68 business tables, ~760k rows.', 'docs/discovery/inventory.md'],
    etl: ['Batch jobs copy OLTP data into the warehouse; reports are a day behind.', 'docs/discovery/dw-lineage.md'],
    dw: ['AdventureWorksDW2022: 12 dimensions and 6 facts plus finance/survey data.', 'docs/discovery/dw-lineage.md'],
    rep: ['Reports on the warehouse.', ''],
    showcase: ['This site: static files on S3 behind CloudFront (origin access control); live APIs optional.', 'showcase/, ADR 0009'],
    newapp: ['.NET 10 app on DynamoDB: browse, search, cart with TTL, checkout with native order ids, order history. IAM task role scoped to aw-catalog/aw-sales/aw-customer.', 'src/AdventureWorks.Web, ADR 0006'],
    oldapp2: ['The original app keeps writing SQL Server during the side-by-side period (decision D4); its changes reach DynamoDB through CDC.', 'docker/before, ADR 0008'],
    rds: ['RDS for SQL Server 2022 Standard (db.m6i.large), CDC on 68 tables with 7-day retention; torn down after every demo.', 'infra/modules/source_db'],
    dms: ['AWS DMS reads the CDC tables and publishes full row images to Kinesis, started from the bulk-load time.', 'infra/modules/cdc, aws/dms'],
    kin: ['Kinesis Data Streams keeps per-key ordering between DMS and the Lambda.', 'infra/modules/cdc'],
    lambda: ['The awcdc transform turns each SQL row into DynamoDB items with mapping.json, enriches join tables from DynamoDB lookups, writes conditionally on log position, tombstones deletes, sends failures to a DLQ.', 'cdc/awcdc, ADR 0005'],
    ddb: ['Seven single-table designs, one per business domain, on-demand capacity, PITR, CMKs on aw-customer / aw-hr.', 'docs/design/dynamodb-design.md, ADR 0001–0004'],
    zetl: ['DynamoDB zero-ETL to Redshift: no pipeline code, one integration per table.', 'infra/modules/warehouse, ADR 0007'],
    rs: ['Typed staging materialized views generated from mapping.json; dw.sp_build_star() rebuilds the star schema hourly.', 'warehouse/, docs/design/warehouse.md'],
    qs: ['QuickSight Enterprise dashboards, only for the showcase (decision W-4).', 'infra/modules/warehouse/quicksight.tf'],
  };
  R.architecture = () => {
    const el = $('#architecture');
    el.innerHTML = `<div class="row" style="align-items:center;justify-content:space-between"><h2>Architecture</h2>
      <div class="seg" id="archseg"><button data-v="before">Before</button><button data-v="after" class="on">After (AWS)</button></div></div>
      <div class="row"><div class="card grow" style="flex:3"><svg id="arch" viewBox="0 0 1000 540" width="100%"></svg></div>
      <div class="card grow" id="archd" style="flex:1"><b>Click a component</b><p class="note">for what it does, why, and where it lives in the repo.</p></div></div>`;
    const draw = v => {
      const A = ARCH[v], W = 150, H = 52, pos = {};
      A.nodes.forEach(n => pos[n[0]] = n);
      let s = `<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="#8792a2"/></marker></defs>`;
      A.lanes.forEach(([t, x]) => s += `<rect class="lane" x="${x - 10}" y="10" width="185" height="520" rx="8"/><text class="lanet" x="${x}" y="30">${esc(t)}</text>`);
      A.edges.forEach(([a, b]) => {
        const p = pos[a], q = pos[b]; const x1 = p[3] + W, y1 = p[4] + H / 2, x2 = q[3], y2 = q[4] + H / 2;
        const back = x2 <= p[3]; const xs = back ? p[3] : x1, xe = back ? q[3] + W : x2;
        const same = q[3] === p[3];
        s += same ? (q[4] > p[4] ? `<path class="edge" d="M${p[3] + W / 2},${p[4] + H} L${q[3] + W / 2},${q[4]}"/>` : `<path class="edge" d="M${p[3] + W / 2},${p[4]} L${q[3] + W / 2},${q[4] + H}"/>`)
          : `<path class="edge" d="M${xs},${y1} C${(xs + xe) / 2},${y1} ${(xs + xe) / 2},${y2} ${xe},${y2}"/>`;
      });
      A.nodes.forEach(([id, t, sub, x, y, c]) => s += `<g class="node ${c}" data-id="${id}" tabindex="0"><rect x="${x}" y="${y}" width="${W}" height="${H}" rx="8"/><text class="t" x="${x + 8}" y="${y + 20}">${esc(t)}</text><text x="${x + 8}" y="${y + 38}" font-size="10">${esc(sub.length > 26 ? sub.slice(0, 25) + '…' : sub)}</text></g>`);
      $('#arch').innerHTML = s;
    };
    $('#archseg').onclick = e => { const v = e.target.dataset.v; if (!v) return; el.querySelectorAll('#archseg button').forEach(b => b.classList.toggle('on', b === e.target)); draw(v); };
    $('#arch').addEventListener('click', e => {
      const g = e.target.closest('.node'); if (!g) return;
      el.querySelectorAll('.node').forEach(n => n.classList.toggle('sel', n === g));
      const id = g.dataset.id, n = [...ARCH.before.nodes, ...ARCH.after.nodes].find(x => x[0] === id), d = DETAILS[id] || ['', ''];
      $('#archd').innerHTML = `<h3 style="margin-top:0">${esc(n[1])}</h3><div class="note">${esc(n[2])}</div><p>${esc(d[0])}</p>${d[1] ? `<p class="note">Repo: <code>${esc(d[1])}</code></p>` : ''}`;
    });
    draw('after');
  };

  // ---------- Data mapping ----------
  R.mapping = () => {
    const el = $('#mapping');
    el.innerHTML = `<div class="row" style="align-items:center;justify-content:space-between"><h2>Data mapping</h2>
      <div class="seg" id="mapseg"><button data-v="ddb" class="on">SQL Server → DynamoDB</button><button data-v="dw">DynamoDB → Redshift star schema</button></div></div><div id="mapbody"></div>`;
    const byTable = {};
    Object.entries(sources).forEach(([s, v]) => (v.items || []).forEach(it => (byTable[it.table] = byTable[it.table] || new Set()).add(s)));
    const ddbView = () => {
      $('#mapbody').innerHTML = `<div class="row"><div class="card" style="width:270px"><input id="msearch" placeholder="Filter SQL tables…" style="width:100%"><div class="list" id="mlist"></div></div>
        <div class="card grow" id="mdetail"></div></div>`;
      const list = () => {
        const f = $('#msearch').value.toLowerCase();
        $('#mlist').innerHTML = tables.map(t => {
          const ss = [...(byTable[t] || [])].filter(s => s.toLowerCase().includes(f)).sort();
          return ss.length ? `<div class="note" style="margin:.5rem 0 .2rem"><b>${t}</b> · ${esc(M.tables[t].domain)}</div>` + ss.map(s => `<div class="i" data-s="${s}">${s} <span class="note">${fmtN(sources[s].row_count)}</span></div>`).join('') : '';
        }).join('');
      };
      const detail = s => {
        const v = sources[s];
        el.querySelectorAll('#mlist .i').forEach(d => d.classList.toggle('on', d.dataset.s === s));
        const keyRows = it => ['PK', 'SK', 'GSI1PK', 'GSI1SK', 'GSI2PK', 'GSI2SK'].filter(k => it[k]).map(k => `<span class="pill k">${k}</span><code>${esc(it[k])}</code>`).join('');
        $('#mdetail').innerHTML = `<h3 style="margin-top:0">${esc(s)} <span class="note">→ ${esc((v.items || []).map(i => i.table + ' / ' + i.entity).join(', '))}</span></h3>
          <div class="note">${fmtN(v.row_count)} rows · primary key ${esc((v.primary_key || []).join(', '))} · domain ${esc(v.domain)}</div>
          <div class="row" style="margin-top:.8rem">${(v.items || []).map(it => `<div class="card grow" style="background:#fffaf2"><b>Item: ${esc(it.entity)}</b> in <code>${esc(it.table)}</code><div class="keys" style="margin-top:.4rem">${keyRows(it)}</div></div>`).join('')}</div>
          ${(v.snapshots || []).length ? `<p><b>Copied (denormalised) attributes</b></p><ul>${v.snapshots.map(x => `<li><code>${esc(x.attrs.join(', '))}</code> from ${esc(x.from)}: <span class="note">${esc(x.refresh)}</span></li>`).join('')}</ul>` : ''}
          <p><b>Columns → attributes</b></p><div style="max-height:330px;overflow:auto"><table class="g"><thead><tr><th>SQL column</th><th>Type</th><th></th><th>DynamoDB attribute</th><th>Transform</th></tr></thead><tbody>
          ${v.columns.map(c => `<tr><td>${esc(c.column)}</td><td class="note">${esc(c.sql_type)}</td><td>→</td><td>${c.transform === 'omitted' ? '<span class="pill oos">omitted</span>' : `<code>${esc(c.attribute)}</code>`}</td><td class="note">${esc(c.transform)}${c.note ? ': ' + esc(c.note) : ''}</td></tr>`).join('')}
          </tbody></table></div>`;
      };
      $('#msearch').oninput = list;
      $('#mlist').onclick = e => { const d = e.target.closest('.i'); if (d) detail(d.dataset.s); };
      list(); detail(sources['Sales.SalesOrderHeader'] ? 'Sales.SalesOrderHeader' : Object.keys(sources)[0]);
    };
    const dwView = () => {
      const L = M.dw_lineage, names = Object.keys(L);
      $('#mapbody').innerHTML = `<div class="row"><div class="card" style="width:270px"><div class="list" id="dlist">${names.map(n => `<div class="i" data-n="${n}">${n.startsWith('Fact') ? '📊' : n.startsWith('Dim') ? '🔷' : '📦'} ${n}</div>`).join('')}</div></div><div class="card grow" id="ddetail"></div></div>`;
      const detail = n => {
        const v = L[n];
        el.querySelectorAll('#dlist .i').forEach(d => d.classList.toggle('on', d.dataset.n === n));
        const from = v.from || [];
        $('#ddetail').innerHTML = `<h3 style="margin-top:0">${esc(n)} <span class="note">→ <code>${esc(v.target)}</code></span></h3>
          <div class="row" style="align-items:stretch">
           <div class="card grow"><b>DynamoDB items (via zero-ETL)</b>${from.map(f => `<div><span class="pill ddb">${esc(f.split('/')[0])}</span> ${esc(f.split('/')[1] || '')}</div>`).join('') || '<div class="note">none: static carry-over</div>'}
           ${(v.static || []).map(f => `<div><span class="pill">static</span> ${esc(f)}</div>`).join('')}</div>
           <div class="arrow">→</div>
           <div class="card grow"><b>Redshift staging</b><div class="note">typed materialized views generated from mapping.json (<code>stg.*</code>)</div></div>
           <div class="arrow">→</div>
           <div class="card grow" style="background:#e9f0fd"><b>${esc(v.target)}</b><div class="note">built by <code>dw.sp_build_star()</code> hourly</div></div></div>
          ${v.filter ? `<p>Filter: <code>${esc(v.filter)}</code></p>` : ''}${v.note ? `<p class="note">${esc(v.note)}</p>` : ''}
          ${v.tables ? `<p><b>Tables:</b> ${v.tables.map(t => `<span class="pill">${esc(t)}</span>`).join('')}</p>` : ''}`;
      };
      $('#dlist').onclick = e => { const d = e.target.closest('.i'); if (d) detail(d.dataset.n); };
      detail('FactInternetSales' in L ? 'FactInternetSales' : names[0]);
    };
    $('#mapseg').onclick = e => { const v = e.target.dataset.v; if (!v) return; el.querySelectorAll('#mapseg button').forEach(b => b.classList.toggle('on', b === e.target)); v === 'ddb' ? ddbView() : dwView(); };
    ddbView();
  };

  // ---------- Access patterns ----------
  R.patterns = () => {
    const el = $('#patterns'), ops = {};
    (M.access_patterns || []).forEach(a => ops[a.id] = a);
    const doms = [...new Set(AP.patterns.map(p => p.domain))];
    el.innerHTML = `<h2>Access patterns <span class="note">${AP.patterns.length} patterns, ${esc(AP.status || '')}</span></h2>
      <div class="row" style="margin-bottom:.7rem"><select id="pdom"><option value="">All domains</option>${doms.map(d => `<option>${esc(d)}</option>`).join('')}</select>
      <select id="pscope"><option value="">All scopes</option><option value="dynamodb">DynamoDB keys</option><option value="redshift">Redshift</option><option value="out-of-scope">Out of scope</option></select>
      <input id="pq" placeholder="Search questions…" size="30"></div><div class="card"><table class="g"><thead><tr><th>ID</th><th>Question</th><th>Scope</th><th>R/W · consistency</th><th>Key conditions (DynamoDB)</th></tr></thead><tbody id="prows"></tbody></table></div>`;
    const draw = () => {
      const d = $('#pdom').value, sc = $('#pscope').value, q = $('#pq').value.toLowerCase();
      $('#prows').innerHTML = AP.patterns.filter(p => (!d || p.domain === d) && (!sc || p.scope === sc) && (!q || (p.id + p.question).toLowerCase().includes(q))).map(p => {
        const o = ops[p.id];
        const pill = p.scope === 'dynamodb' ? 'ddb' : p.scope === 'redshift' ? 'rs' : 'oos';
        return `<tr data-id="${p.id}"><td><b>${p.id}</b><div class="note">${esc(p.domain)}</div></td><td>${esc(p.question)}<div class="note">${esc(p.frequency)}</div></td>
          <td><span class="pill ${pill}">${esc(p.scope)}</span>${o ? `<div class="note">${esc(o.table)}</div>` : ''}</td><td>${esc(p.read_write)} · ${esc(p.consistency)}</td>
          <td>${o ? o.ops.map(x => `<div class="op">${esc(x)}</div>`).join('') + (o.result ? `<div class="note">${esc(o.result)}</div>` : '') : `<span class="note">${p.scope === 'redshift' ? 'served by Redshift (zero-ETL), no keys' : '–'}</span>`}</td></tr>`;
      }).join('');
    };
    ['pdom', 'pscope', 'pq'].forEach(i => $('#' + i).oninput = draw);
    draw();
  };

  // ---------- Live replication (Phase 4 monitor, embedded) ----------
  R.replication = () => {
    const api = cfg.monitorApi ?? '';
    const live = cfg.monitorMode === 'live';
    $('#replication').innerHTML = `<h2>Live replication <span class="pill ${live ? 'ddb' : ''}">${live ? 'live API' : 'recorded replay'}</span></h2>
      <p class="note">${live ? 'Streaming from the CDC consumer API.' : 'Showing a recorded sample of the Phase 4 end-to-end test (demo order → DynamoDB). Run <code>scripts/showcase-up.sh --live</code> with the CDC stack up to stream real changes.'} Click a row to compare the SQL row with the DynamoDB items it became.</p>
      <iframe id="monitor" title="Replication monitor" src="monitor.html?api=${encodeURIComponent(api)}" style="height:640px"></iframe>`;
  };

  // ---------- The app ----------
  R.app = () => {
    const url = cfg.appUrl || '';
    // An https page cannot frame an http app (mixed content): link only until the ALB has a certificate.
    const mixed = location.protocol === 'https:' && /^http:/i.test(url);
    $('#app').innerHTML = `<div class="row" style="align-items:center;justify-content:space-between"><h2>The .NET 10 shopper app</h2>
      ${url ? `<a class="b" id="applink" href="${esc(url)}" target="_blank" rel="noopener" style="text-decoration:none">Open in a new tab ↗</a>` : ''}</div>
      <div class="row"><div class="card grow" style="flex:3">${mixed ? `<p>The app runs at <a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>. It is served over HTTP, so it opens in a new tab (set <code>certificate_arn</code> to embed it here).</p>` : url ? `<iframe id="appframe" title="AdventureWorks app" src="${esc(url)}" style="height:640px"></iframe>`
        : `<p>No app URL configured. Start it locally (<code>scripts/after-up.sh</code>) and run <code>scripts/showcase-up.sh --app-url http://localhost:5080</code>, or deploy it to AWS (ALB URL is set automatically).</p>`}</div>
      <div class="card grow" style="flex:1"><b>Try it</b><ol><li>Log in with the demo customer</li><li>Browse a category, search “mountain”</li><li>Add to cart, check out</li><li>Open <i>My orders</i>: read-after-write, strongly consistent</li></ol>
      <p class="note">Pages are served by DynamoDB queries (see Access Patterns CAT-*, SAL-*, CUS-*). The task role can only reach aw-catalog, aw-sales and aw-customer.</p></div></div>`;
  };

  show(location.hash.slice(1) || 'presentation');
})();
