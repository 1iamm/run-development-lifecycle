(() => {
  let pending=false;
  document.addEventListener('change',async event=>{
    const input=event.target;
    if(!input.matches('input[data-item]'))return;
    if(pending){input.checked=!input.checked;return;}
    pending=true;
    const checked=input.checked,status=document.getElementById('checklist-status');
    const inputs=[...document.querySelectorAll('input[data-item]')];
    inputs.forEach(i=>i.disabled=true);
    status.textContent='正在保存确认记录…';
    try{
      const config=await (await fetch('/api/workspace',{cache:'no-store'})).json();
      const result=await fetch('/api/tasks/'+input.dataset.task+'/checklist',{method:'POST',headers:{'Content-Type':'application/json','X-Lifecycle-Token':config.csrf},body:JSON.stringify({phaseId:input.dataset.phase,itemId:input.dataset.item,checked,expectedRevision:Number(input.dataset.revision)})});
      const value=await result.json();
      if(!result.ok)throw new Error(value.error||'保存失败');
      inputs.filter(i=>i.dataset.phase===input.dataset.phase).forEach(i=>i.dataset.revision=String(value.revision));
      input.parentElement.querySelector('small').textContent=value.checkedAt;
      status.textContent='已保存你的确认；任务阶段与审批状态保持原有记录。';
    }catch(error){input.checked=!checked;status.textContent='未保存：'+error.message+'。如数据已更新，请刷新页面后重试。';}
    finally{pending=false;inputs.forEach(i=>i.disabled=false);}
  });
})();
