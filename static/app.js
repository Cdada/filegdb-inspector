"use strict";
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="local-token"]').content;
let scan = null, selected = new Set(), result = null, rows = [], page = 0, busy = false, ready = false;
const pageSize = 200;
async function api(path, body) {
  const response = await fetch(path, {method:body === undefined ? "GET" : "POST",
    headers:{"X-Local-Token":token, ...(body === undefined ? {} : {"Content-Type":"application/json"})},
    ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 ${response.status}`);
  return data;
}
function message(text="") { $("message").textContent = text; }
function setBusy(value) {
  busy = value;
  for (const id of ["choose","scan","all","none","manual"]) $(id).disabled = value;
  $("folder").readOnly = value || !$("manual").checked;
  document.querySelectorAll('#gdb-list input').forEach(input => input.disabled = value);
  updateSelection();
}
function updateSelection() {
  $("selection-count").textContent = scan ? `已选择 ${selected.size} / ${scan.gdbs.length}` : "尚未扫描";
  $("analyze").disabled = busy || !ready || selected.size === 0;
}
function cell(row, value, className="") {
  const td = document.createElement("td"); td.textContent = value ?? "—";
  td.className = className; row.append(td); return td;
}
function drawGDBs() {
  $("gdb-list").replaceChildren();
  for (const item of scan.gdbs) {
    const tr = document.createElement("tr"), check = document.createElement("input");
    check.type = "checkbox"; check.checked = selected.has(item.path);
    check.setAttribute("aria-label", `选择 ${item.name}`);
    check.onchange = () => {check.checked ? selected.add(item.path) : selected.delete(item.path); updateSelection();};
    cell(tr, "").append(check); cell(tr,item.gdb_index); cell(tr,item.directory); cell(tr,item.name);
    $("gdb-list").append(tr);
  }
  if (!scan.gdbs.length) {const tr=document.createElement("tr");cell(tr,"未发现 .gdb 文件夹。","empty").colSpan=4;$("gdb-list").append(tr);}
  updateSelection();
}
$("choose").onclick = async () => {
  setBusy(true); message("请在 macOS 文件夹选择窗口中选择目录。");
  try {const value=await api("/api/select-folder"); if (!value.cancelled) $("folder").value=value.path;message();}
  catch (error) {message(error.message + "。可按 README 开启备用手工路径输入。");}
  finally {setBusy(false);}
};
$("manual").onchange = () => $("folder").readOnly = !$("manual").checked;
$("scan").onclick = async () => {
  setBusy(true);message("正在扫描目录，请稍候…");
  try {scan=await api("/api/scan",{root:$("folder").value});selected=new Set();drawGDBs();
    $("folder").value=scan.root;$("scan-errors").textContent=scan.errors.map(e=>`${e.code} ${e.path}: ${e.message}`).join("\n");
    message(`扫描完成：发现 ${scan.gdbs.length} 个 GDB。请勾选需要读取的数据库。`);}
  catch(error){message(error.message);}
  finally{setBusy(false);}
};
$("all").onclick = () => {if(scan){selected=new Set(scan.gdbs.map(g=>g.path));drawGDBs();}};
$("none").onclick = () => {if(scan){selected.clear();drawGDBs();}};
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
$("analyze").onclick = async () => {
  setBusy(true);message();result=null;rows=[];renderRows();$("download").disabled=true;$("overview").replaceChildren();
  $("errors").textContent="正在读取…";$("logs").textContent="";$("task-state").textContent="读取中";
  try {
    const task=await api("/api/analyze",{scan_id:scan.scan_id,paths:[...selected]});
    let failures=0;
    while(true){
      let info;
      try{info=await api(`/api/tasks/${task.task_id}`);failures=0;message();}
      catch(error){if(++failures>=5)throw error;message("进度连接暂时中断，正在重试；后台任务不会重复提交。");await sleep(2000);continue;}
      const p=info.progress;
      $("progress").textContent=`正在处理 ${p.gdb_current} / ${p.gdb_total} 个 GDB · ${p.gdb_name||""} · 当前图层：${p.layer_name||"准备中"} (${p.layer_current||0}/${p.layer_total||0}) · 已读取 ${(p.records_read||0).toLocaleString()} 条`;
      $("progress-bar").max=p.gdb_total;$("progress-bar").value=Math.max(0,p.gdb_current-1);
      $("logs").textContent=info.logs.join("\n");
      if(info.status!=="running"){
        result=await api(`/api/tasks/${task.task_id}/results`);loadResults();
        $("task-state").textContent=info.status==="completed"?"检查完成":info.status==="failed"?"任务失败":"完成，存在异常";
        $("progress").textContent=info.status==="failed"?`任务失败：${info.error}`:`已完成 ${p.gdb_total} 个 GDB，异常 ${result.errors.length} 条。`;
        if(info.status!=="failed")$("progress-bar").value=p.gdb_total;
        if(info.error)message(info.error);
        break;
      }
      await sleep(900);
    }
  }catch(error){message(error.message + "。如任务已提交，请查看本地日志与 runtime/exports；不要立即重复提交。");$("task-state").textContent="连接或任务异常";}
  finally{setBusy(false);}
};
const types={spatial_layer:"空间图层",non_spatial_table:"非空间表",other:"其他"};
const statuses={success:"正常",partial:"部分异常",failed:"读取失败"};
function loadResults(){
  rows=[];$("overview").replaceChildren();$("filter-gdb").replaceChildren(new Option("全部 GDB",""));
  for(const gdb of result.gdbs){
    const option=new Option(`${gdb.gdb_index}. ${gdb.name}`,gdb.path);$("filter-gdb").append(option);
    const card=document.createElement("div");card.className="card";
    const title=document.createElement("strong");title.textContent=`${gdb.gdb_index}. ${gdb.name}`;card.append(title);
    const p=document.createElement("p"),s=gdb.summary||{};
    p.textContent=`空间图层 ${s.spatial_layers??"—"} · 普通表 ${s.tables??"—"} · 字段 ${s.fields??"—"} · 异常 ${gdb.errors.length}`;card.append(p);
    const detail=document.createElement("p");detail.textContent=`${statuses[gdb.status]||gdb.status} · ${gdb.driver||"驱动未打开"}`;card.append(detail);$("overview").append(card);
    if(!gdb.layers.length&&gdb.errors.length)rows.push({g:gdb,l:{},f:{},exception:true});
    for(const layer of gdb.layers){
      if(!layer.fields.length)rows.push({g:gdb,l:layer,f:{},exception:layer.status!=="success"});
      for(const field of layer.fields)rows.push({g:gdb,l:layer,f:field,exception:layer.status==="failed"||field.status==="failed"});
    }
  }
  $("errors").textContent=result.errors.length?result.errors.map(e=>`${e.code} | ${e.path||""} | ${e.layer_name||""} | ${e.field_name||""}\n${e.message}`).join("\n\n"):"暂无异常。";
  $("download").disabled=false;page=0;renderRows();
}
function visibleRows(){
  const query=id=>$(id).value.trim().toLocaleLowerCase();
  const gl=query("filter-layer"),gf=query("filter-field"),ga=query("filter-alias"),gp=$("filter-gdb").value;
  const data=rows.filter(r=>(!gp||r.g.path===gp)&&(!gl||(r.l.layer_name||"").toLocaleLowerCase().includes(gl))&&
    (!gf||(r.f.field_name||"").toLocaleLowerCase().includes(gf))&&(!ga||(r.f.field_alias||"").toLocaleLowerCase().includes(ga))&&
    (!$("only-null").checked||r.f.null_count>0)&&(!$("only-errors").checked||r.exception)&&
    (!$("hide-system").checked||r.f.field_category!=="系统字段"));
  const base=(a,b)=>a.g.gdb_index-b.g.gdb_index||(a.l.layer_name||"").localeCompare(b.l.layer_name||"","zh-CN")||
    (a.l.fields||[]).indexOf(a.f)-(b.l.fields||[]).indexOf(b.f);
  const sort=$("sort").value;
  data.sort((a,b)=>{
    if(sort==="layer")return (a.l.layer_name||"").localeCompare(b.l.layer_name||"","zh-CN")||base(a,b);
    if(sort==="count")return (b.l.feature_count??-1)-(a.l.feature_count??-1)||base(a,b);
    if(sort==="null")return (b.f.null_rate??-1)-(a.f.null_rate??-1)||base(a,b);
    return base(a,b);
  });return data;
}
const percent=value=>value==null?"—":(value*100).toFixed(2)+"%";
function renderRows(){
  const data=visibleRows(),pages=Math.ceil(data.length/pageSize);page=Math.max(0,Math.min(page,pages-1));
  $("result-list").replaceChildren();
  for(const r of data.slice(page*pageSize,(page+1)*pageSize)){
    const tr=document.createElement("tr"),g=r.g,l=r.l,f=r.f;
    const values=[g.gdb_index,g.directory,g.name,types[l.object_type]||"其他",l.layer_name,
      l.feature_count??(r.exception?"读取失败":"—"),f.field_name,f.field_alias,f.field_type,f.field_category,
      f.null_count,percent(f.null_rate),f.empty_string_count,f.whitespace_string_count,percent(f.blank_rate),
      r.exception?"读取失败":f.reason==="geometry_not_counted"?"几何不参与统计":f.reason==="empty_layer"?"空图层":statuses[l.status]||statuses[g.status]];
    values.forEach((value,i)=>cell(tr,value,i===11?"rate":i===15&&r.exception?"bad":""));
    $("result-list").append(tr);
  }
  if(!data.length){const tr=document.createElement("tr");cell(tr,result?"没有符合筛选条件的结果。":"统计结果将显示在这里。","empty").colSpan=16;$("result-list").append(tr);}
  $("row-count").textContent=`显示 ${data.length} / ${rows.length} 条`;
  $("page").textContent=`第 ${pages?page+1:0} / ${pages} 页 · 每页 ${pageSize} 条`;
  $("prev").disabled=page===0;$("next").disabled=page+1>=pages;
}
for(const id of ["filter-gdb","filter-layer","filter-field","filter-alias","sort","only-null","only-errors","hide-system"]){$(id).addEventListener("input",()=>{page=0;renderRows();});}
$("prev").onclick=()=>{page--;renderRows();};$("next").onclick=()=>{page++;renderRows();};
$("download").onclick=()=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json;charset=utf-8"}));
  const a=document.createElement("a");a.href=url;a.download=`FileGDB检查_${result.task_id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
(async()=>{try{
  const env=await api("/api/environment");ready=env.ready;
  $("environment").textContent=`GDAL ${env.gdal_version||"不可用"} · OpenFileGDB：${env.openfilegdb?"可用":"不可用"} · 字段别名 API：${env.alias_api?"可用":"不可用"} · 只读模式`;
  $("env-details").textContent=`Python：${env.python_path}\nosgeo：${env.osgeo_path||"—"}\n日志：${env.log_path}\n${(env.warnings||[]).join("\n")}`;
  $("manual-box").hidden=!env.allow_manual_path;
  if(!env.folder_picker){
    $("choose").disabled=true;
    if(env.allow_manual_path)$("manual").click();
  }
  if(!ready)message(env.error||"环境不可用，请通过 start.command 启动。");
  updateSelection();renderRows();
}catch(error){message(error.message);}})();
