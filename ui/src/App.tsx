import { useEffect, useMemo, useState } from "react"
import { Bug, Check, CheckSquare2, Columns3, Copy, Goal, LayoutList, Moon, Plus, Sparkles, Sun } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"

type ItemType = "Epic" | "Feature" | "Task" | "Bug"
type Status = "open" | "inprogress" | "closed" | "resolved" | "blocked"
type Priority = "low" | "medium" | "high" | "urgent"
type Project = { id: string; name: string; created_at: string; updated_at: string }
type Item = { id: string; title: string; type: ItemType; description: string; parent_id: string | null; project_id: string; status: Status; priority: Priority; created_at: string; updated_at: string }
type Draft = Pick<Item, "title" | "type" | "description" | "parent_id" | "project_id" | "status" | "priority"> & { id?: string }

const typeMeta = {
  Epic: { icon: Goal, tone: "text-violet-600 bg-violet-500/10 border-violet-500/20" },
  Feature: { icon: Sparkles, tone: "text-blue-600 bg-blue-500/10 border-blue-500/20" },
  Task: { icon: CheckSquare2, tone: "text-emerald-600 bg-emerald-500/10 border-emerald-500/20" },
  Bug: { icon: Bug, tone: "text-rose-600 bg-rose-500/10 border-rose-500/20" },
} as const
const statusMeta: Record<Status, { label: string; tone: string }> = {
  open: { label: "Open", tone: "text-sky-700 bg-sky-500/10 border-sky-500/20" },
  inprogress: { label: "In progress", tone: "text-violet-700 bg-violet-500/10 border-violet-500/20" },
  closed: { label: "Closed", tone: "text-zinc-600 bg-zinc-500/10 border-zinc-500/20" },
  resolved: { label: "Resolved", tone: "text-emerald-700 bg-emerald-500/10 border-emerald-500/20" },
  blocked: { label: "Blocked", tone: "text-rose-700 bg-rose-500/10 border-rose-500/20" },
}
const priorityMeta: Record<Priority, { label: string; tone: string }> = {
  low: { label: "Low", tone: "text-zinc-600 bg-zinc-500/10 border-zinc-500/20" },
  medium: { label: "Medium", tone: "text-amber-700 bg-amber-500/10 border-amber-500/20" },
  high: { label: "High", tone: "text-orange-700 bg-orange-500/10 border-orange-500/20" },
  urgent: { label: "Urgent", tone: "text-rose-700 bg-rose-500/10 border-rose-500/20" },
}
const statuses = Object.keys(statusMeta) as Status[]
const priorities = Object.keys(priorityMeta) as Priority[]

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || "Something went wrong")
  return body
}

function TypeMark({ type, size = "normal" }: { type: ItemType; size?: "normal" | "small" }) {
  const { icon: Icon, tone } = typeMeta[type]
  return <span className={`inline-flex shrink-0 items-center justify-center rounded ${tone} ${size === "small" ? "size-5" : "size-6"}`}><Icon className={size === "small" ? "size-3" : "size-3.5"} aria-hidden="true" /><span className="sr-only">{type}</span></span>
}
function TypeBadge({ type }: { type: ItemType }) { return <Badge variant="outline" className={`gap-1 border ${typeMeta[type].tone}`}><TypeMark type={type} size="small" />{type}</Badge> }
function StatusBadge({ status }: { status: Status }) { return <Badge variant="outline" className={`border ${statusMeta[status].tone}`}>{statusMeta[status].label}</Badge> }
function PriorityBadge({ priority }: { priority: Priority }) { return <Badge variant="outline" className={`border ${priorityMeta[priority].tone}`}>{priorityMeta[priority].label}</Badge> }

function Tree({ items, parentId, depth, onSelect, onAddChild }: { items: Item[]; parentId: string | null; depth: number; onSelect: (item: Item) => void; onAddChild: (id: string) => void }) {
  const children = items.filter((item) => item.parent_id === parentId)
  if (!children.length) return null
  return <ul className={depth ? "ml-4 border-l border-border/70 pl-3" : "space-y-1"}>{children.map((item) => <li key={item.id} className="group/list"><div className="flex min-w-0 items-center gap-1 rounded-lg pr-1 hover:bg-muted/80"><span className="size-6 shrink-0" aria-hidden="true" /><button type="button" onClick={() => onSelect(item)} className="flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"><TypeMark type={item.type} /><span className="min-w-0 flex-1 truncate font-medium">{item.title}</span><span className="flex shrink-0 gap-1"><StatusBadge status={item.status} /><PriorityBadge priority={item.priority} /></span></button><Button variant="ghost" size="icon-xs" className="invisible shrink-0 group-hover/list:visible" onClick={() => onAddChild(item.id)} aria-label={`Add child to ${item.title}`}><Plus /></Button></div><Tree items={items} parentId={item.id} depth={depth + 1} onSelect={onSelect} onAddChild={onAddChild} /></li>)}</ul>
}

function StatusBoard({ items, onSelect }: { items: Item[]; onSelect: (item: Item) => void }) {
  return <div className="flex gap-3 overflow-x-auto pb-4" aria-label="Status board">{statuses.map((status) => { const columnItems = items.filter((item) => item.status === status); return <section key={status} className="w-64 shrink-0 rounded-xl bg-muted/50 p-3"><header className="mb-3 flex items-center justify-between"><StatusBadge status={status} /><span className="text-xs text-muted-foreground">{columnItems.length}</span></header><div className="space-y-2">{columnItems.length ? columnItems.map((item) => <button key={item.id} type="button" onClick={() => onSelect(item)} className="w-full rounded-lg border bg-background p-3 text-left shadow-sm transition hover:border-foreground/20"><div className="flex items-start gap-2"><TypeMark type={item.type} /><span className="min-w-0 flex-1 text-sm font-medium leading-5">{item.title}</span></div><div className="mt-3 flex gap-1"><TypeBadge type={item.type} /><PriorityBadge priority={item.priority} /></div></button>) : <p className="px-1 py-5 text-center text-xs text-muted-foreground">No items</p>}</div></section> })}</div>
}

function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [projectId, setProjectId] = useState("")
  const [view, setView] = useState<"tree" | "board">("tree")
  const [draft, setDraft] = useState<Draft | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [projectDialog, setProjectDialog] = useState(false)
  const [projectName, setProjectName] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [dark, setDark] = useState(() => localStorage.getItem("work-items-theme") === "dark")
  const [copied, setCopied] = useState(false)

  const visibleItems = useMemo(() => items.filter((item) => item.project_id === projectId), [items, projectId])
  const currentProject = projects.find((project) => project.id === projectId)
  const typeCounts = useMemo(() => Object.fromEntries((Object.keys(typeMeta) as ItemType[]).map((type) => [type, visibleItems.filter((item) => item.type === type).length])), [visibleItems])
  const blockedParents = useMemo(() => { if (!draft?.id) return new Set<string>(); const blocked = new Set([draft.id]); const addChildren = (id: string) => visibleItems.filter((item) => item.parent_id === id).forEach((item) => { blocked.add(item.id); addChildren(item.id) }); addChildren(draft.id); return blocked }, [draft?.id, visibleItems])

  const setItemUrl = (itemId: string) => { const url = new URL(window.location.href); url.searchParams.set("item", itemId); window.history.pushState(null, "", url) }
  const clearItemUrl = () => { const url = new URL(window.location.href); url.searchParams.delete("item"); window.history.replaceState(null, "", url) }
  const load = async () => {
    setLoading(true)
    try {
      const [nextProjects, nextItems] = await Promise.all([request<Project[]>("/api/projects"), request<Item[]>("/api/items")])
      const linkedItem = nextItems.find((item) => item.id === new URLSearchParams(window.location.search).get("item"))
      setProjects(nextProjects); setItems(nextItems)
      setProjectId(linkedItem?.project_id || ((current) => nextProjects.some((project) => project.id === current) ? current : (nextProjects[0]?.id || "")))
      if (linkedItem) { setExpanded(false); setDraft({ ...linkedItem }) }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load workspace") }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); localStorage.setItem("work-items-theme", dark ? "dark" : "light") }, [dark])

  const openItem = (item: Item) => { setError(""); setExpanded(false); setCopied(false); setDraft({ ...item }); setItemUrl(item.id) }
  const copyItemLink = async (itemId: string) => { const url = new URL(window.location.href); url.searchParams.set("item", itemId); await navigator.clipboard.writeText(url.toString()); setCopied(true); window.setTimeout(() => setCopied(false), 1500) }
  const openNew = (parentId: string | null = null) => { if (!projectId) return setProjectDialog(true); clearItemUrl(); setError(""); setExpanded(false); setDraft({ title: "", type: "Task", description: "", parent_id: parentId, project_id: projectId, status: "open", priority: "medium" }) }
  const save = async () => { if (!draft) return; setError(""); try { const item = await request<Item>(draft.id ? `/api/items/${draft.id}` : "/api/items", { method: draft.id ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) }); await load(); setDraft(item); setItemUrl(item.id) } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save item") } }
  const createProject = async () => { setError(""); try { const project = await request<Project>("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: projectName }) }); setProjectName(""); setProjectDialog(false); await load(); setProjectId(project.id) } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create project") } }

  return <div className="min-h-svh bg-[#f8f8f8] text-foreground"><div className="min-h-svh bg-background"><main className="min-w-0"><header className="flex min-h-14 flex-wrap items-center gap-3 border-b px-4 py-2 sm:px-6"><div className="min-w-32"><h1 className="text-sm font-semibold">Work items</h1><p className="text-[11px] text-muted-foreground">Local-first workspace</p></div><Select value={projectId} onValueChange={(id) => { setProjectId(id); setDraft(null); clearItemUrl() }} disabled={!projects.length}><SelectTrigger aria-label="Project" className="w-48"><SelectValue placeholder="Select a project" /></SelectTrigger><SelectContent>{projects.map((project) => <SelectItem key={project.id} value={project.id}>{project.name}</SelectItem>)}</SelectContent></Select><Button variant="outline" size="sm" onClick={() => { setError(""); setProjectDialog(true) }}><Plus />Project</Button><div className="ml-auto flex items-center gap-2"><Sun className="size-4 text-muted-foreground" aria-hidden="true" /><Switch checked={dark} onCheckedChange={setDark} aria-label="Dark theme" /><Moon className="size-4 text-muted-foreground" aria-hidden="true" /><Button onClick={() => openNew()} className="gap-1.5"><Plus />New item</Button></div></header><div className="mx-auto max-w-6xl px-4 py-7 sm:px-8"><div className="flex flex-col gap-5 border-b pb-5 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-sm text-muted-foreground">{currentProject ? `${currentProject.name} work` : "Create a project to begin."}</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">{currentProject?.name || "Projects"}</h2></div>{currentProject && <div className="flex flex-wrap items-center gap-2"><div className="flex rounded-lg border bg-muted/40 p-0.5"><Button size="sm" variant={view === "tree" ? "secondary" : "ghost"} onClick={() => setView("tree")}><LayoutList />Tree</Button><Button size="sm" variant={view === "board" ? "secondary" : "ghost"} onClick={() => setView("board")}><Columns3 />Status board</Button></div>{(Object.keys(typeMeta) as ItemType[]).map((type) => <Badge key={type} variant="outline" className="shrink-0 gap-1.5 py-1"><TypeMark type={type} size="small" />{typeCounts[type]} {type}{typeCounts[type] === 1 ? "" : "s"}</Badge>)}</div>}</div><section className="mt-5" aria-label={view === "tree" ? "Work item tree" : "Work item status board"}>{loading ? <p className="py-10 text-sm text-muted-foreground">Loading your workspace…</p> : !currentProject ? <div className="rounded-xl border border-dashed px-6 py-14 text-center"><span className="mx-auto mb-3 grid size-10 place-items-center rounded-xl bg-muted"><Goal className="size-5 text-muted-foreground" /></span><h3 className="font-semibold">Create your first project</h3><p className="mt-1 text-sm text-muted-foreground">Projects keep independent work trees separate.</p><Button className="mt-4" onClick={() => setProjectDialog(true)}><Plus />New project</Button></div> : visibleItems.length ? view === "tree" ? <Tree items={visibleItems} parentId={null} depth={0} onSelect={openItem} onAddChild={openNew} /> : <StatusBoard items={visibleItems} onSelect={openItem} /> : <div className="rounded-xl border border-dashed px-6 py-14 text-center"><span className="mx-auto mb-3 grid size-10 place-items-center rounded-xl bg-muted"><Goal className="size-5 text-muted-foreground" /></span><h3 className="font-semibold">Begin with a work item</h3><p className="mt-1 text-sm text-muted-foreground">{currentProject.name} is ready for its first Epic, Feature, Task, or Bug.</p><Button className="mt-4" onClick={() => openNew()}><Plus />Create item</Button></div>}</section></div></main></div>

    <Dialog open={projectDialog} onOpenChange={setProjectDialog}><DialogContent><DialogHeader><DialogTitle>New project</DialogTitle><DialogDescription>Projects have independent work-item trees.</DialogDescription></DialogHeader><label className="text-sm font-medium">Project name<Input className="mt-2" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="e.g. Website refresh" autoFocus /></label>{error && <p className="text-sm text-destructive" role="alert">{error}</p>}<DialogFooter><Button variant="ghost" onClick={() => setProjectDialog(false)}>Cancel</Button><Button onClick={() => void createProject()}>Create project</Button></DialogFooter></DialogContent></Dialog>

    <Sheet open={Boolean(draft)} onOpenChange={(open) => { if (!open) { setDraft(null); setExpanded(false); clearItemUrl() } }}><SheetContent side="right" className={`flex w-full flex-col gap-0 p-0 sm:max-w-[540px] ${expanded ? "!w-full !max-w-none" : ""}`}>{draft && <><SheetHeader className="border-b px-5 py-4 text-left"><div className="flex items-center gap-2"><TypeMark type={draft.type} /><SheetTitle>{draft.id ? "Edit work item" : "New work item"}</SheetTitle>{draft.id && <Button variant="ghost" size="icon-xs" className="ml-auto" onClick={() => void copyItemLink(draft.id!)} aria-label="Copy item link" title="Copy item link">{copied ? <Check /> : <Copy />}</Button>}</div><SheetDescription>{draft.id ? "Keep scope and hierarchy clear." : `Add work to ${currentProject?.name || "this project"}.`}</SheetDescription></SheetHeader><div className="flex items-center justify-between border-b px-5 py-2"><div className="flex gap-1"><TypeBadge type={draft.type} /><StatusBadge status={draft.status} /><PriorityBadge priority={draft.priority} /></div><Button variant="ghost" size="sm" onClick={() => setExpanded((value) => !value)}>{expanded ? "Return to tree" : "Expand details"}</Button></div><div className="flex-1 overflow-y-auto px-5 py-6"><div className="space-y-5"><label className="block text-sm font-medium">Title<Input aria-label="Title" className="mt-2 h-10 text-base" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="Describe the outcome" autoFocus /></label><div className="grid gap-5 sm:grid-cols-2"><label className="block text-sm font-medium">Type<Select value={draft.type} onValueChange={(type: ItemType) => setDraft({ ...draft, type })}><SelectTrigger aria-label="Type" className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(typeMeta) as ItemType[]).map((type) => <SelectItem key={type} value={type}><span className="flex items-center gap-2"><TypeMark type={type} size="small" />{type}</span></SelectItem>)}</SelectContent></Select></label><label className="block text-sm font-medium">Status<Select value={draft.status} onValueChange={(status: Status) => setDraft({ ...draft, status })}><SelectTrigger aria-label="Status" className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent>{statuses.map((status) => <SelectItem key={status} value={status}><StatusBadge status={status} /></SelectItem>)}</SelectContent></Select></label><label className="block text-sm font-medium">Priority<Select value={draft.priority} onValueChange={(priority: Priority) => setDraft({ ...draft, priority })}><SelectTrigger aria-label="Priority" className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent>{priorities.map((priority) => <SelectItem key={priority} value={priority}><PriorityBadge priority={priority} /></SelectItem>)}</SelectContent></Select></label><label className="block text-sm font-medium">Parent<Select value={draft.parent_id || "none"} onValueChange={(parent_id) => setDraft({ ...draft, parent_id: parent_id === "none" ? null : parent_id })}><SelectTrigger aria-label="Parent" className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">No parent</SelectItem>{visibleItems.filter((item) => !blockedParents.has(item.id)).map((item) => <SelectItem key={item.id} value={item.id}><span className="flex items-center gap-2"><TypeMark type={item.type} size="small" />{item.title}</span></SelectItem>)}</SelectContent></Select></label></div><label className="block text-sm font-medium">Description<Textarea aria-label="Description" className="mt-2 min-h-36" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="What should happen, and why?" /></label>{error && <p className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>}</div></div><footer className="flex items-center justify-between border-t px-5 py-4"><Button variant="ghost" onClick={() => openNew(draft.id || null)}><Plus />Add child</Button><div className="flex gap-2"><Button variant="ghost" onClick={() => setDraft(null)}>Cancel</Button><Button onClick={() => void save()}>Save item</Button></div></footer></>}</SheetContent></Sheet>
  </div>
}

export default App
