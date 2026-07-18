"""Apply all LearningPathPage changes in one pass."""
import re

with open('src/pages/LearningPathPage.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

def replace(old, new, label=''):
    global content, changes
    if old in content:
        content = content.replace(old, new)
        changes += 1
        if label: print(f'  OK: {label}')
    else:
        print(f'  MISS: {label}')

# 1. Imports
replace(
    "import { useState, useRef, useEffect } from 'react';",
    "import { useState, useRef, useEffect, useMemo, useCallback } from 'react';",
    'useMemo import'
)
replace(
    "import { enableProfileExtraction, listPlanningDrafts } from '../api/learningPath';",
    "import { enableProfileExtraction, listPlanningDrafts } from '../api/learningPath';\nimport DayPlanView from '../components/learning/DayPlanView';\nimport MasteryBarGroup from '../components/learning/MasteryBarGroup';",
    'DayPlanView+MasteryBarGroup import'
)

# 2. Lock + tab state
replace(
    '  const hasInj = stages.some(s => (s.tasks || []).some((t: any) =>\n    t.source === \'remedial\' || t._adjustment === \'remedial\' || t._adjustment === \'strengthened\'\n  ));',
    '  const hasInj = stages.some(s => (s.tasks || []).some((t: any) =>\n    t.source === \'remedial\' || t._adjustment === \'remedial\' || t._adjustment === \'strengthened\'\n  ));\n\n  // \u2500\u2500 Lock + tab + recommendation state \u2500\u2500\n  const { currentStageIdx, currentTaskIdx } = useMemo(() => {\n    for (let si = 0; si < stages.length; si++) {\n      const tasks = stages[si].tasks || [];\n      for (let ti = 0; ti < tasks.length; ti++) {\n        if (tasks[ti].status !== \'completed\' && tasks[ti].status !== \'mastered\')\n          return { currentStageIdx: si, currentTaskIdx: ti };\n      }\n    }\n    return { currentStageIdx: stages.length, currentTaskIdx: -1 };\n  }, [stages]);\n  const [middleTab, setMiddleTab] = useState<\'tasks\' | \'recommendations\'>(\'tasks\');\n  const [recommendedResources, setRecommendedResources] = useState<any[]>([]);\n  const [recommendLoading, setRecommendLoading] = useState(false);',
    'lock+tab state'
)

# 3. activeStageIdx + fetchRecommendations
replace(
    '  const activeStage = stages.find(s => s.id === activeStageId) || stages[firstIncompleteIdx] || stages[0];\n\n  return (',
    '  const activeStage = stages.find(s => s.id === activeStageId) || stages[firstIncompleteIdx] || stages[0];\n  const activeStageIdx = stages.findIndex(s => s.id === activeStage?.id);\n\n  const fetchRecommendations = useCallback(async () => {\n    if (!sessionId || !activeStageId) return;\n    setRecommendLoading(true);\n    try {\n      const r = await fetch(\'/api/resources/recommendations/for-learning\', {\n        method: \'POST\', headers: { \'Content-Type\': \'application/json\' },\n        body: JSON.stringify({ sessionId, stageId: activeStageId }),\n      }).then(res => res.json());\n      setRecommendedResources(r?.data?.recommendations?.resources || []);\n    } catch { setRecommendedResources([]); }\n    finally { setRecommendLoading(false); }\n  }, [sessionId, activeStageId]);\n\n  useEffect(() => {\n    if (middleTab === \'recommendations\') fetchRecommendations();\n  }, [middleTab, fetchRecommendations]);\n\n  return (',
    'activeStageIdx+fetch'
)

# 4. Tab bar
replace(
    '                  {/* \u9636\u6bb5\u4f53 \u2014\u2014 \u59cb\u7ec8\u5c55\u5f00 */}\n                  <div className="border-t border-surface-200 px-5 pb-5 pt-5 sm:px-6 sm:pb-6 space-y-4">',
    '                  {/* \u2500\u2500 \u6807\u7b7e\u5207\u6362 \u2500\u2500 */}\n                  <div className="flex gap-2 px-5 pt-4 sm:px-6">\n                    <button type="button" onClick={() => setMiddleTab(\'tasks\')}\n                      className={\'text-[11px] font-medium tracking-wide pb-1 border-b-2 \' + (middleTab===\'tasks\'?\'border-primary-400 text-surface-700\':\'border-transparent text-surface-400 hover:text-surface-500\')}\n                    >\u4efb\u52a1</button>\n                    <button type="button" onClick={() => setMiddleTab(\'recommendations\')}\n                      className={\'text-[11px] font-medium tracking-wide pb-1 border-b-2 \' + (middleTab===\'recommendations\'?\'border-primary-400 text-surface-700\':\'border-transparent text-surface-400 hover:text-surface-500\')}\n                    >\u63a8\u8350\u8d44\u6e90</button>\n                  </div>\n                  {/* \u9636\u6bb5\u4f53 \u2014\u2014 \u59cb\u7ec8\u5c55\u5f00 */}\n                  <div className="border-t border-surface-200 px-5 pb-5 pt-5 sm:px-6 sm:pb-6 space-y-4">',
    'tab bar'
)

# 5. Lock on task button
replace(
    '                              <button type="button" disabled={done}',
    '                              <button type="button" disabled={done || (activeStageIdx > currentStageIdx || (activeStageIdx === currentStageIdx && ti > currentTaskIdx))}',
    'lock disabled'
)

# 6. Recommendations section - wrap tasks in ternary and add reco section
replace(
    '                  </div>\n                </article>\n              );\n            })()}\n          </section>\n\n          {/* \u2550\u2550\u2550 \u53f3\u680f\uff1a\u7acb\u5373\u5f00\u59cb + \u5b66\u4e60\u5206\u6790 + \u7ec3\u4e60 \u2550\u2550\u2550 */}',
    '                  </div>\n                ) : (\n                  <div className="space-y-4">\n                    {recommendLoading ? (\n                      <div className="flex items-center justify-center py-10">\n                        <Loader2 size={24} className="animate-spin text-surface-300" />\n                        <span className="ml-3 text-sm text-surface-400">\u6b63\u5728\u641c\u7d22\u63a8\u8350\u8d44\u6e90...</span>\n                      </div>\n                    ) : recommendedResources.length === 0 ? (\n                      <div className="text-center py-10">\n                        <BookOpen size={40} className="mx-auto mb-3 text-surface-300" />\n                        <p className="text-sm text-surface-500">\u6682\u65e0\u63a8\u8350\u8d44\u6e90</p>\n                        <button onClick={fetchRecommendations} className="mt-3 text-xs text-primary-500 hover:underline">\u70b9\u51fb\u91cd\u8bd5</button>\n                      </div>\n                    ) : (\n                      <div className="grid grid-cols-1 gap-3">\n                        {recommendedResources.map((r: any, i: number) => (\n                          <a key={i} href={r.url || \'#\'} target="_blank" rel="noopener noreferrer"\n                            className="flex items-start gap-3 rounded-xl border border-surface-100 p-3 hover:border-primary-200 hover:bg-primary-50/30 transition-all h-[72px] overflow-hidden">\n                            <span className="mt-0.5 shrink-0 text-lg">{r.type===\'video\'?\'\U0001f3ac\':r.type===\'article\'?\'\U0001f4c4\':r.type===\'course\'?\'\U0001f393\':\'\U0001f4d6\'}</span>\n                            <span className="min-w-0 flex-1">\n                              <span className="block text-sm font-semibold text-surface-800 truncate">{r.title}</span>\n                              <span className="mt-1 block text-xs text-surface-400 line-clamp-2">{r.snippet || r.description || \'\'}</span>\n                            </span>\n                          </a>\n                        ))}\n                      </div>\n                    )}\n                  </div>\n                )}\n                </article>\n              );\n            })()}\n          </section>\n\n          {/* \u2550\u2550\u2550 \u53f3\u680f\uff1a\u7acb\u5373\u5f00\u59cb + \u5b66\u4e60\u5206\u6790 + \u7ec3\u4e60 \u2550\u2550\u2550 */}',
    'recommendation section'
)

# 7. Wrap task content in ternary
replace(
    '                    <p className="max-w-2xl text-sm leading-7 text-surface-500">{stage.objective || stage.theme || \'\'}</p>',
    '                    {middleTab === \'tasks\' ? (\n                    <>\n                    <p className="max-w-2xl text-sm leading-7 text-surface-500">{stage.objective || stage.theme || \'\'}</p>',
    'task ternary open'
)

# 8. Close the task ternary fragment
replace(
    '                    </div>\n                  </div>\n                ) : (',
    '                    </div>\n                  </>\n                  </div>\n                ) : (',
    'task ternary close'
)

# 9. DayPlanView
replace(
    '            )}\n            <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">\n              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-surface-400">\u5b66\u4e60\u5206\u6790</p>',
    '            )}\n            {path?.day_plan && (\n              <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">\n                <DayPlanView dayPlan={path.day_plan} totalDays={estimatedDays} currentDay={1} />\n              </section>\n            )}\n            <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">\n              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-surface-400">\u5b66\u4e60\u5206\u6790</p>',
    'DayPlanView'
)

# 10. MasteryBarGroup
replace(
    '              </ul>\n            </section>',
    '              </ul>\n              {path?.diagnosis?.mastery_levels && (\n                <MasteryBarGroup items={path.diagnosis.mastery_levels as any[]} max={5} />\n              )}\n            </section>',
    'MasteryBarGroup'
)

with open('src/pages/LearningPathPage.tsx', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nTotal: {changes}/10 changes applied')
