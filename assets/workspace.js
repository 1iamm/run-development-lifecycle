(() => {
  'use strict';
  const kinds=['product','technical','ui','development','testing','release'];
  const labels=['产品','技术','UI','开发','测试','上线'];
  const artifactLabels=['产品 PRD','技术设计','UI 与交互稿','开发记录','测试用例与结果','上线资源与检查表'];
  const states={active:'进行中',wait:'待你确认',blocked:'已阻塞',done:'已完成'};
  const query=new URLSearchParams(location.search);
  let tasks=[],selected=query.get('task'),view='board',token='',busy=false,detailSequence=0,signature='';
  const $=s=>document.querySelector(s);
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=x=>x?new Date(x).toLocaleDateString('zh-CN'):'—';
  const badge=t=>`<span class="badge ${t.status}">${states[t.status]}</span>`;
  const conversation=t=>t.thread_id?`<a href="codex://threads/${encodeURIComponent(t.thread_id)}" class="button">打开 Codex 对话 ↗</a>`:'<span class="small muted">尚未绑定 Codex 对话</span>';
  const progress=t=>`<div class="progress-label"><span class="muted">${t.total?`${t.completed}/${t.total} 子项`:t.status==='done'?'已完成':'待拆分子项'}</span><span>${t.progress===null?'—':t.progress+'%'}</span></div>${t.progress===null?'':`<progress class="progress" value="${t.progress}" max="100" aria-label="任务完成进度">${t.progress}%</progress>`}`;
  const archiveButton=(t,compact=false)=>`<button class="${compact?'text-button':'button primary'}" type="button" data-archive="${t.key}" aria-label="归档任务与对话：${esc(t.title)}" title="${t.thread_id?'手动归档，保留当前阶段和进度':'需要先关联对应的 Codex 对话'}" ${busy||t.archive_state==='copying'||!t.thread_id?'disabled':''}>${t.archive_state==='failed'||t.archive_state==='uncertain'?'重试归档':compact?'归档':'归档任务与对话'}</button>`;
  async function api(path,options={}){
    const result=await fetch(path,{cache:'no-store',...options});
    const value=await result.json();
    if(!result.ok)throw new Error(value.error||'请求失败');
    return value;
  }
  function showError(message){$('#error').hidden=!message;$('#error').textContent=message||'';}
  function remember(){history.replaceState(null,'',selected?'/?task='+encodeURIComponent(selected):'/');}
  function render(){
    const active=tasks.filter(t=>t.archive_state!=='archived'),archived=tasks.filter(t=>t.archive_state==='archived');
    $('#archive-count').textContent=archived.length;
    $('#page-title').textContent=view==='board'?'迭代看板':'归档';
    $('#summary').textContent=view==='board'?`${new Set(active.map(t=>t.project)).size} 个项目 · ${active.filter(t=>t.status!=='done').length} 项推进中 · ${active.filter(t=>t.status==='done').length} 项已完成待归档`:`${archived.length} 项任务 · 由你手动归档`;
    $('#board-view').hidden=view!=='board';$('#archive-view').hidden=view!=='archive';
    document.querySelectorAll('[data-view]').forEach(el=>{if(el.dataset.view===view)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    $('#board').innerHTML=kinds.map((kind,index)=>{
      const group=active.filter(t=>t.stage===kind);
      return `<section class="column"><div class="column-heading"><h2><span class="dot" aria-hidden="true"></span>${labels[index]}</h2><span class="column-count">${group.length}</span></div><div class="cards">${group.map(t=>`<article class="task-card-shell"><button type="button" class="task-card" data-task="${t.key}" aria-pressed="${selected===t.key}"><span class="project-name">${esc(t.project)}</span><span class="task-name">${esc(t.title)}</span>${badge(t)}<div>${progress(t)}</div><span class="card-next">${esc(t.status==='done'?'已完成，等待你手动归档':t.nextAction||'待更新下一步')}${t.archive?.error?`<br>归档未完成：${esc(t.archive.error)}`:''}</span><span class="card-meta"><span>${esc(t.taskId)}</span><span>${esc(t.activePhase)}</span></span></button><div class="card-actions">${archiveButton(t,true)}</div></article>`).join('')||'<p class="empty">暂无任务</p>'}</div></section>`;
    }).join('');
    $('#task-count').textContent=active.length+' 项';
    $('#task-table').innerHTML=active.map(t=>`<tr class="${selected===t.key?'selected':''}"><td><button class="text-button" type="button" data-task="${t.key}">${esc(t.title)}</button><div class="task-id">${esc(t.taskId)}</div></td><td>${esc(t.project)}</td><td>${labels[kinds.indexOf(t.stage)]} · ${esc(t.activePhase)}</td><td>${badge(t)}</td><td class="table-progress">${progress(t)}</td><td class="table-next">${esc(t.status==='done'?'等待你手动归档':t.nextAction)}</td><td>${esc(t.targetDate||'待设置')}</td><td><div class="row-actions">${t.thread_id?`<a href="codex://threads/${encodeURIComponent(t.thread_id)}">对话 ↗</a>`:'<span class="muted">未绑定对话</span>'}${archiveButton(t,true)}</div></td></tr>`).join('')||'<tr><td colspan="8" class="empty">新建或导入 lifecycle 任务后，将自动出现在这里。</td></tr>';
    $('#archive-table').innerHTML=archived.map(t=>`<tr class="${selected===t.key?'selected':''}"><td><button class="text-button" type="button" data-task="${t.key}">${esc(t.title)}</button><div class="task-id">${esc(t.taskId)}</div></td><td>${esc(t.project)}</td><td>${labels[kinds.indexOf(t.stage)]} · ${esc(t.activePhase)}<div>${badge(t)}</div></td><td>${date(t.archive.archived_at)}</td><td><span class="badge ${t.archive.copy_state==='saved'?'done':''}">${t.archive.copy_state==='saved'?'保留中':'已清理'}</span></td><td>${date(t.archive.expires_at)}</td><td>${conversation(t)}<div class="task-id">已归档 · 继续保留</div></td></tr>`).join('')||'<tr><td colspan="7" class="empty">任何阶段的任务都可以手动归档，归档保留当时的阶段与进度。</td></tr>';
    $('#detail').hidden=true;$('#archive-detail').hidden=true;
    if(selected)loadDetail(selected);
  }
  async function loadDetail(key){
    const sequence=++detailSequence;
    try{
      const d=await api('/api/tasks/'+key);
      if(sequence!==detailSequence||key!==selected)return;
      const t=d.summary,archived=t.archive_state==='archived',container=$(archived?'#archive-detail':'#detail');
      if((archived?'archive':'board')!==view)return;
      const expired=archived&&t.archive.copy_state==='deleted';
      container.hidden=false;
      const phaseRows=Object.values(d.phases).map(p=>`<div class="phase"><span>${esc(p.id)} · ${esc(p.name)}</span><span class="muted">${esc(p.state)}</span></div>`).join('');
      const artifacts=expired?'<p class="muted small">本地归档副本已到期清理。Codex 中的已归档对话继续保留。</p>':kinds.map((kind,index)=>`<a class="artifact" href="/tasks/${key}/documents/${kind}">${artifactLabels[index]}<span>${d.deliverables.filter(a=>a.kind===kind).length?d.deliverables.filter(a=>a.kind===kind).length+' 份文件':'结构化记录'} ↗</span></a>`).join('');
      container.innerHTML=`<div class="detail-head"><div class="eyebrow"><span>${esc(t.project)} / ${esc(t.taskId)}</span><button type="button" class="close" data-close aria-label="收起任务详情">×</button></div><h2>${esc(t.title)}</h2>${badge(t)} <span class="badge">${labels[kinds.indexOf(t.stage)]}</span><div class="detail-actions">${conversation(t)}${archived?'':archiveButton(t)}<span class="small muted">${archived?`本地副本${expired?'已清理':'保留至 '+date(t.archive.expires_at)}`:'任意阶段可手动归档 · 保留当前进度 · 本地副本保留 30 天'}</span></div></div><div class="detail-body"><section><h3>${archived?'归档记录':'阶段与下一步'}</h3><div class="phases">${phaseRows}</div><div class="next"><span class="muted">${archived?'已归档 · 对话保留':'下一步'}</span><p>${esc(archived?'归档于 '+date(t.archive.archived_at):t.status==='done'?'已完成，等待你手动归档':t.nextAction)}</p></div>${t.archive?.error?`<p class="small">归档错误：${esc(t.archive.error)}</p>`:''}<details class="history"><summary>最近记录 · 共 ${d.events.length} 条</summary>${d.events.slice(-12).reverse().map(e=>`<p><span class="muted">${date(e.at)}</span> ${esc(e.summary)}</p>`).join('')}</details></section><section><div class="section-heading"><h3>交付物</h3><span class="small muted">独立页面</span></div>${artifacts}</section></div>`;
    }catch(error){showError(error.message);}
  }
  async function refresh(force=false){
    try{
      const value=await api('/api/workspace');token=value.csrf;
      const next=JSON.stringify(value.tasks);
      tasks=value.tasks;
      if(selected&&tasks.find(t=>t.key===selected)?.archive_state==='archived')view='archive';
      $('#database-path').textContent=value.database;
      $('#sync-state').textContent='已同步 · '+new Date().toLocaleTimeString('zh-CN');
      if(value.cleanupError)showError('自动清理失败：'+value.cleanupError);
      if(force||next!==signature){signature=next;render();}
    }catch(error){showError('本地服务连接失败：'+error.message);$('#sync-state').textContent='连接已中断 · 显示上次数据';}
  }
  document.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.view){view=button.dataset.view;selected=null;remember();render();return;}
    if(button.dataset.task){selected=button.dataset.task;remember();render();return;}
    if(button.hasAttribute('data-close')){const previous=selected;selected=null;remember();render();document.querySelector(`[data-task="${previous}"]`)?.focus();return;}
    if(button.dataset.archive&&!busy){
      const key=button.dataset.archive;busy=true;showError('');$('#notice').textContent='正在保存本地快照并归档 Codex 对话…';render();
      try{
        await api('/api/tasks/'+key+'/archive',{method:'POST',headers:{'Content-Type':'application/json','X-Lifecycle-Token':token},body:JSON.stringify({userRequested:true})});
        selected=key;view='archive';remember();$('#notice').textContent='任务与 Codex 对话已归档，本地副本保留 30 天。';
      }catch(error){showError('归档未完成：'+error.message);$('#notice').textContent='任务仍保留在看板，可处理后重试。';}
      finally{busy=false;await refresh(true);}
    }
  });
  refresh(true);
  setInterval(()=>{if(!document.hidden&&!busy)refresh();},5000);
})();
