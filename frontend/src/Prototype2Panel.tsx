import { useState } from "react";
import { apiBaseUrl } from "./api";

type Criterion = { id: string; name: string; description: string };
type Choice = { id: string; points: string; parameters: Record<string, unknown> };
type Result = { total: string; response: string; saved: boolean; criteria: Array<{id:string;name:string;earned:string;maximum:string;evidence:string}> };

export default function Prototype2Panel() {
  const [prompt,setPrompt] = useState("Return a JSON object with name and age.");
  const [model,setModel] = useState("gpt-4o-mini");
  const [catalog,setCatalog] = useState<Criterion[]>([]);
  const [choices,setChoices] = useState<Choice[]>([]);
  const [responseOverride,setResponseOverride] = useState("");
  const [result,setResult] = useState<Result|null>(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const total = choices.reduce((sum,c) => sum + Math.round(Number(c.points)*100),0);
  const valid = choices.length>0 && total===10000 && choices.every(c => /^\d+(\.\d{1,2})?$/.test(c.points) && Number(c.points)>0);
  async function post(path:string,payload:unknown) {
    const response = await fetch(apiBaseUrl+"/prototype2/"+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail==="string" ? data.detail : "Request failed");
    return data;
  }
  async function suggest() {
    setBusy(true);setError("");setResult(null);
    try {
      const [catalogResponse,suggestions] = await Promise.all([fetch(apiBaseUrl+"/prototype2/catalog"),post("suggest",{prompt})]);
      if (!catalogResponse.ok) throw new Error("Could not load criteria catalog");
      setCatalog(await catalogResponse.json());
      const proposed:Criterion[] = suggestions.suggestions;
      setChoices(proposed.map((c,i) => ({id:c.id,points:String(Math.floor(100/proposed.length)+(i===0?100%proposed.length:0)),parameters:c.id==="required_keys"?{keys:["name","age"]}:c.id==="field_types"?{types:{name:"string",age:"number"}}:c.id==="minimum_length"?{min_chars:20}:c.id==="keywords"?{terms:["name","age"]}:c.id==="forbidden_terms"?{terms:["error"]}:{}})));
    } catch (e) {setError(e instanceof Error?e.message:"Suggestion failed");}
    finally {setBusy(false);}
  }
  function change(id:string,patch:Partial<Choice>) {setChoices(old=>old.map(c=>c.id===id?{...c,...patch}:c));setResult(null);}
  async function run() {
    setBusy(true);setError("");setResult(null);
    try {setResult(await post("evaluate",{prompt,model,scoring:{criteria:choices},...(responseOverride?{response_override:responseOverride}:{})}));}
    catch(e){setError(e instanceof Error?e.message:"Evaluation failed");}
    finally{setBusy(false);}
  }
  return <section className="panel run-form" style={{padding:20,marginTop:20}}>
    <h2>Prototype 2: AI-Suggested Criteria</h2>
    <label className="field">Prompt<textarea value={prompt} onChange={e=>setPrompt(e.target.value)} rows={4}/></label>
    <button type="button" className="primary-button" disabled={busy||!prompt.trim()} onClick={suggest}>Suggest criteria with GPT-4o mini</button>
    {catalog.length>0&&<><h3>Approve criteria and points</h3><p>Total: {(total/100).toFixed(2)} / 100.00</p>
      {catalog.map(item=>{const c=choices.find(x=>x.id===item.id);return <div key={item.id} style={{marginBottom:14}}>
        <label><input type="checkbox" checked={!!c} onChange={e=>{setChoices(old=>e.target.checked?[...old,{id:item.id,points:"1",parameters:{}}]:old.filter(x=>x.id!==item.id));setResult(null);}}/> {item.name}</label>
        <small style={{display:"block"}}>{item.description}</small>
        {c&&<><label>Points <input type="number" min="0.01" step="0.01" value={c.points} onChange={e=>change(item.id,{points:e.target.value})}/></label>
          {["required_keys","keywords","forbidden_terms"].includes(item.id)&&<label>Terms <input value={String((c.parameters[item.id==="required_keys"?"keys":"terms"] as string[]|undefined)?.join(", ")??"")} onChange={e=>change(item.id,{parameters:{[item.id==="required_keys"?"keys":"terms"]:e.target.value.split(",").map(x=>x.trim()).filter(Boolean)}})}/></label>}
          {item.id==="minimum_length"&&<label>Minimum characters <input type="number" min="1" value={Number(c.parameters.min_chars??20)} onChange={e=>change(item.id,{parameters:{min_chars:Number(e.target.value)}})}/></label>}
          {item.id==="field_types"&&<label>Field types JSON <input value={JSON.stringify(c.parameters.types??{})} onChange={e=>{try{change(item.id,{parameters:{types:JSON.parse(e.target.value)}});}catch{setError("Invalid field types JSON");}}}/></label>}
        </>}
      </div>;})}
      <label className="field">Model<input value={model} onChange={e=>setModel(e.target.value)}/></label>
      <label className="field">Optional test response<textarea rows={3} value={responseOverride} onChange={e=>setResponseOverride(e.target.value)}/></label>
      <button type="button" className="primary-button" disabled={!valid||busy} onClick={run}>Run approved criteria</button>
      {!valid&&<p>Weights must total exactly 100.00.</p>}
    </>}
    {error&&<p role="alert">{error}</p>}
    {result&&<div><h3>Score: {result.total} / 100.00</h3><p>Not saved to PostgreSQL yet.</p><pre style={{whiteSpace:"pre-wrap"}}>{result.response}</pre>{result.criteria.map(c=><p key={c.id}><strong>{c.name}: {c.earned} / {c.maximum}</strong> — {c.evidence}</p>)}</div>}
  </section>;
}