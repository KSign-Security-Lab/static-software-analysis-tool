"use client";

import { AlertTriangle, ChevronDown, Search } from "lucide-react";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Dev-only: every vendored primitive, in both themes, side by side.
 *
 * The token mapping in theme.css cannot be reviewed on paper -- `--color-accent`
 * meaning "hover grey" to shadcn and "brand teal" to us is the kind of thing
 * that only looks wrong. This page is where it gets looked at, before forty
 * components depend on it.
 *
 * It also proves the `@theme inline` choice: the two panels below are the same
 * markup under a nested `data-theme`, and they only differ if utilities resolve
 * their roles at the element rather than once at :root.
 *
 * Delete this route when the workbench is done.
 */

// Every class below is written out in full. Tailwind scans for literal
// strings, so a template like `bg-${name}` generates nothing at all -- and the
// swatch would silently render transparent, which is exactly the failure this
// page exists to catch.
const SSAT_ROLES: [string, string][] = [
  ["bg", "bg-bg"],
  ["surface", "bg-surface"],
  ["surface-2", "bg-surface-2"],
  ["surface-3", "bg-surface-3"],
  ["field", "bg-field"],
  ["line", "bg-line"],
  ["line-2", "bg-line-2"],
  ["line-3", "bg-line-3"],
  ["ink", "bg-ink"],
  ["ink-strong", "bg-ink-strong"],
  ["ink-muted", "bg-ink-muted"],
  ["ink-faint", "bg-ink-faint"],
  ["accent-ink", "bg-accent-ink"],
  ["accent-solid", "bg-accent-solid"],
  ["accent-wash", "bg-accent-wash"],
  ["alt", "bg-alt"],
  ["alt-wash", "bg-alt-wash"],
  ["danger", "bg-danger"],
  ["danger-wash", "bg-danger-wash"],
  ["warn", "bg-warn"],
  ["warn-wash", "bg-warn-wash"],
  ["ok", "bg-ok"],
  ["ok-wash", "bg-ok-wash"],
];

const SHADCN_ROLES: [string, string][] = [
  ["background", "bg-background"],
  ["foreground", "bg-foreground"],
  ["card", "bg-card"],
  ["popover", "bg-popover"],
  ["primary", "bg-primary"],
  ["primary-foreground", "bg-primary-foreground"],
  ["secondary", "bg-secondary"],
  ["muted", "bg-muted"],
  ["muted-foreground", "bg-muted-foreground"],
  ["accent", "bg-accent"],
  ["accent-foreground", "bg-accent-foreground"],
  ["destructive", "bg-destructive"],
  ["border", "bg-border"],
  ["input", "bg-input"],
  ["ring", "bg-ring"],
];

const SEVERITIES: [string, string][] = [
  ["치명적", "bg-sev-critical"],
  ["높음", "bg-sev-high"],
  ["보통", "bg-sev-medium"],
  ["낮음", "bg-sev-low"],
  ["정보", "bg-sev-info"],
];

const TYPE_SCALE: [string, string][] = [
  ["text-2xs", "text-2xs"],
  ["text-xs", "text-xs"],
  ["text-sm", "text-sm"],
  ["text-base", "text-base"],
  ["text-md", "text-md"],
  ["text-lg", "text-lg"],
  ["text-xl", "text-xl"],
  ["text-2xl", "text-2xl"],
];

function Swatches({ title, roles, note }: { title: string; roles: [string, string][]; note: string }) {
  return (
    <div>
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
      <p className="mt-0.5 mb-2 text-2xs text-muted-foreground">{note}</p>
      <div className="grid grid-cols-2 gap-1">
        {roles.map(([name, cls]) => (
          <div key={name} className="flex items-center gap-2 rounded-sm border border-border p-1">
            <span className={`size-6 shrink-0 rounded-xs border border-border ${cls}`} />
            <code className="truncate text-2xs">{name}</code>
          </div>
        ))}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  );
}

function Panel({ theme }: { theme: "dark" | "light" }) {
  return (
    <TooltipProvider>
      <div
        data-theme={theme}
        className="min-w-0 space-y-6 rounded-lg border border-border bg-background p-5 text-foreground"
      >
        <header className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">{theme}</h2>
          <code className="text-2xs text-muted-foreground">data-theme=&quot;{theme}&quot;</code>
        </header>

        <Swatches
          title="SSAT 역할"
          roles={SSAT_ROLES}
          note="컴포넌트가 참조하는 이름. 램프 단계는 직접 쓰지 않습니다."
        />
        <Swatches
          title="shadcn 계약"
          roles={SHADCN_ROLES}
          note="같은 역할을 가리킵니다. accent 는 브랜드가 아니라 hover 배경입니다."
        />

        <Section title="심각도">
          <div className="flex flex-wrap gap-1.5">
            {SEVERITIES.map(([label, dot]) => (
              <span
                key={label}
                className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-2xs font-medium"
              >
                <span className={`size-2 rounded-full ${dot}`} />
                {label}
              </span>
            ))}
          </div>
        </Section>

        <Section title="타입 스케일">
          <div className="space-y-0.5">
            {TYPE_SCALE.map(([label, cls]) => (
              <p key={label} className={cls}>
                <span className="text-muted-foreground">{label}</span> 핸들러 해석과 근거 추적 ·
                handle_update_firmware
              </p>
            ))}
            <p className="font-mono text-sm">font-mono · sprintf(cmd, &quot;wget %s&quot;, url); · 한글 혼용</p>
          </div>
        </Section>

        <Section title="버튼">
          <div className="flex flex-wrap items-center gap-2">
            <Button>기본</Button>
            <Button variant="secondary">보조</Button>
            <Button variant="outline">외곽선</Button>
            <Button variant="ghost">고스트</Button>
            <Button variant="destructive">삭제</Button>
            <Button variant="link">링크</Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm">작게</Button>
            <Button size="lg">크게</Button>
            <Button size="icon" aria-label="검색">
              <Search />
            </Button>
            <Button disabled>비활성</Button>
          </div>
        </Section>

        <Section title="배지">
          <div className="flex flex-wrap gap-2">
            <Badge>기본</Badge>
            <Badge variant="secondary">보조</Badge>
            <Badge variant="destructive">위험</Badge>
            <Badge variant="outline">외곽선</Badge>
          </div>
        </Section>

        <Section title="폼">
          <div className="space-y-2">
            <Label htmlFor={`f-${theme}`}>파일 이름</Label>
            <Input id={`f-${theme}`} placeholder="main.c" />
            <Textarea placeholder="설명을 입력하세요" rows={2} />
            <Select>
              <SelectTrigger>
                <SelectValue placeholder="예제 선택…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="a">update_firmware.c</SelectItem>
                <SelectItem value="b">remote_start.c</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <Checkbox id={`c-${theme}`} defaultChecked />
              <Label htmlFor={`c-${theme}`}>중단점 설정</Label>
            </div>
            <Slider defaultValue={[42]} max={100} />
            <ToggleGroup type="single" defaultValue="tree" variant="outline">
              <ToggleGroupItem value="tree">호출 순서</ToggleGroupItem>
              <ToggleGroupItem value="chat">대화로 보기</ToggleGroupItem>
            </ToggleGroup>
          </div>
        </Section>

        <Section title="상태">
          <Progress value={62} />
          <Alert>
            <AlertTriangle />
            <AlertTitle>모델 미설정</AlertTitle>
            <AlertDescription>AGENT_MODEL 이 설정되지 않았습니다.</AlertDescription>
          </Alert>
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>실행 실패</AlertTitle>
            <AlertDescription>엔드포인트에 연결할 수 없습니다.</AlertDescription>
          </Alert>
          <div className="space-y-1">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
          </div>
        </Section>

        <Section title="표면">
          <Tabs defaultValue="one">
            <TabsList>
              <TabsTrigger value="one">문제</TabsTrigger>
              <TabsTrigger value="two">트레이스</TabsTrigger>
            </TabsList>
            <TabsContent value="one" className="pt-2 text-sm text-muted-foreground">
              탭 내용
            </TabsContent>
            <TabsContent value="two" className="pt-2 text-sm text-muted-foreground">
              두 번째
            </TabsContent>
          </Tabs>

          <Accordion type="single" collapsible>
            <AccordionItem value="a">
              <AccordionTrigger>근거 패키지</AccordionTrigger>
              <AccordionContent>유입 → 전파 → 위험 지점</AccordionContent>
            </AccordionItem>
          </Accordion>

          <div className="flex flex-wrap gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm">
                  툴팁
                </Button>
              </TooltipTrigger>
              <TooltipContent>EXACT_IDENTIFIER</TooltipContent>
            </Tooltip>

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm">
                  팝오버
                </Button>
              </PopoverTrigger>
              <PopoverContent className="text-sm">중단점을 고르세요.</PopoverContent>
            </Popover>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  메뉴 <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem>캐시 무시하고 재검사</DropdownMenuItem>
                <DropdownMenuItem>실행 중단</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                  대화상자
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>새 파일</DialogTitle>
                  <DialogDescription>이름을 입력하세요.</DialogDescription>
                </DialogHeader>
                <Input placeholder="new.c" />
              </DialogContent>
            </Dialog>
          </div>

          <Separator />

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>검사</TableHead>
                <TableHead>상태</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>입력 검증</TableCell>
                <TableCell className="text-ok">관측됨</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>경로 정규화</TableCell>
                <TableCell className="text-danger">누락</TableCell>
              </TableRow>
            </TableBody>
          </Table>

          <ScrollArea className="h-20 rounded-sm border border-border p-2">
            <p className="text-sm text-muted-foreground">
              스크롤 영역. 이 안에서 스크롤바가 애플리케이션의 나머지 부분과 같아 보여야 합니다.
              {" ".repeat(4)}
              한 줄 더. 또 한 줄. 또 한 줄. 또 한 줄. 또 한 줄. 또 한 줄.
            </p>
          </ScrollArea>
        </Section>
      </div>
    </TooltipProvider>
  );
}

export default function TokensPage() {
  return (
    <div className="min-h-0 overflow-auto p-6">
      <header className="mb-4">
        <h1 className="text-xl font-semibold">디자인 토큰 · 프리미티브</h1>
        <p className="text-sm text-muted-foreground">
          같은 마크업, 중첩된 data-theme 두 개. 두 패널이 다르게 보이면 역할이 요소 단위로 해석되고 있다는 뜻입니다.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel theme="dark" />
        <Panel theme="light" />
      </div>
    </div>
  );
}
