"""Tie a host visual assessment to measured frames, areas and a revision decision."""
import json

if __package__:
    from .evidence import native_box
else:
    from evidence import native_box


def decide(inspection, source_hash, rows):
    if not isinstance(inspection, dict) or inspection.get("source_sha256") != source_hash:
        raise ValueError("Select the inspection for this source.")
    current = rows[-1]
    if inspection.get("candidate_sha256") != current["sha256"]:
        raise ValueError("Select the inspection for the final candidate.")
    parent = None
    if "parent_sha256" in inspection:
        parent = next((r for r in rows[:-1] if r["sha256"] == inspection["parent_sha256"]), None)
        if parent is None:
            raise ValueError("Include the inspected parent among the earlier candidates.")
    checks = inspection.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("Provide visual checks for the subject and its critical junctions.")
    evidence = []
    retry = False
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("Provide each visual check as an object.")
        name = check.get("region")
        status = check.get("status")
        if not isinstance(name, str) or name not in current["wavelet"] or status not in ("aligned", "revise", "uncertain"):
            raise ValueError("Select a measured region and an inspection status.")
        for field in ("source_evidence", "candidate_evidence", "next_action"):
            if not isinstance(check.get(field), str) or not check[field].strip():
                raise ValueError(f"Describe {field} for each visual check.")
        interpretation = current.get("interpretation", {}).get(name)
        if interpretation and status == "aligned" and (not isinstance(check.get("semantic_evidence"), str) or not check["semantic_evidence"].strip()):
            check = dict(check, status="uncertain",
                         next_action=f"Inspect the native crop for this interpretation: {interpretation}")
            status = check["status"]
        scores = current["wavelet"][name]
        item = dict(check)
        if parent and name in parent["wavelet"] and (name == "full" or
                tuple(parent["inspection_regions"][name]) == tuple(current["inspection_regions"][name])):
            previous = parent["wavelet"][name]
            item["a1_mae_delta"] = scores[0]["low_rgb_mae"] - previous[0]["low_rgb_mae"]
            item["a4_mae_delta"] = scores[-1]["low_rgb_mae"] - previous[-1]["low_rgb_mae"]
        retry |= status != "aligned"
        evidence.append(item)
    checked = {item["region"] for item in evidence}
    required = {"full": "Inspect the whole source frame.", **current.get("source_relationships", {})}
    for name, observation in required.items():
        if name not in checked:
            retry = True
            evidence.append({"region": name, "source_evidence": observation, "status": "uncertain",
                             "candidate_evidence": "Candidate inspection pending.",
                             "next_action": "Compare this source relationship with the native output."})
    decision = {"checks": evidence, "source_sha256": source_hash, "candidate_sha256": current["sha256"],
                "parent_sha256": parent["sha256"] if parent else None}
    if "native_review" in inspection:
        native = inspection["native_review"]
        if not isinstance(native, dict) or native.get("status") not in ("aligned", "uncertain", "revise"):
            raise ValueError("Choose a native inspection status.")
        for key in ("region", "detail_gain", "continuity"):
            if not isinstance(native.get(key), str) or not native[key].strip():
                raise ValueError(f"Describe native_review.{key}.")
        if native["region"] not in current["inspection_regions"]:
            raise ValueError("Choose a measured crop for native_review.")
        if native["status"] != "aligned":
            if not isinstance(native.get("next_action"), str) or not native["next_action"].strip():
                raise ValueError("Describe the next native repair in next_action.")
            retry = True
        decision["native_review"] = native
    decision["action"] = "revise" if retry else "retain"
    return decision


def revision_feedback(row, assessment):
    checks = assessment.get("checks", [])
    repairs = [c for c in checks if c["status"] != "aligned"]
    native = assessment.get("native_review")
    if native and native["status"] != "aligned":
        region = native["region"]
        repairs.append(dict(region=region, candidate_evidence=native["detail_gain"] + " " + native["continuity"],
                            source_evidence=row.get("source_relationships", {}).get(region, "Preserve the source geometry."),
                            next_action=native["next_action"]))
    feedback = dict(parent_sha256=row["sha256"], region="full", observed="", change="", preserve="", retained=[])
    if repairs:
        first = repairs[0]
        feedback.update(region=first["region"], observed=first["candidate_evidence"], change=first["next_action"],
                        preserve=first["source_evidence"],
                        retained=[c["candidate_evidence"] for c in checks if c["status"] == "aligned"],
                        remaining=[{"region": c["region"], "change": c["next_action"]} for c in repairs[1:]])
    return feedback


def decision_page(decision):
    rows = []
    lines = []
    for check in decision["checks"]:
        rows.append([check["region"], check["source_evidence"], check["candidate_evidence"], check["status"]])
        lines.append(f"{check['region']}: {check['next_action']}")
        if check.get("semantic_evidence"):
            lines.append(f"{check['region']} visible interpretation: {check['semantic_evidence']}")
        if check.get("residual_evidence"):
            lines.append(f"{check['region']} source grid: {check['residual_evidence']}")
        if "a1_mae_delta" in check:
            lines.append(f"Change from parent in this area: A1 MAE {check['a1_mae_delta']:+.2f}, "
                         f"A4 MAE {check['a4_mae_delta']:+.2f}.")
    native = decision.get("native_review")
    if native:
        lines.extend([native["detail_gain"], native["continuity"]])
        if native.get("next_action"):
            lines.append(native["next_action"])
    return {"title": "Visual decision / " + decision["action"],
            "note": "The visual host compares source and native evidence. Deltas use candidate minus parent.",
            "columns": ["Region", "Source evidence", "Candidate evidence", "Assessment"],
            "rows": rows, "lines": lines}


def workflow_pages(workflow, source_hash, rows, images, original, final=False):
    """Resolve a recorded execution graph and publish its visual and measured evidence."""
    if not isinstance(workflow, dict) or workflow.get("source_sha256") != source_hash:
        raise ValueError("Use the workflow for the measured source.")
    stages = workflow.get("stages")
    if not isinstance(stages, list) or len(stages) != len(rows):
        raise ValueError("Record one stage for each candidate in command-line order.")
    by_hash = {}
    trace = []
    pages = []
    for number, (stage, row) in enumerate(zip(stages, rows), 1):
        if not isinstance(stage, dict):
            raise ValueError("Supply a stage object.")
        for key in ("tool", "reason"):
            if not isinstance(stage.get(key), str) or not stage[key].strip():
                raise ValueError(f"Describe the stage {key}.")
        parameters = stage.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError("Supply stage parameters as a JSON object.")
        inspection = dict(stage, source_sha256=source_hash)
        decision = decide(inspection, source_hash, rows[:number])
        if row["sha256"] in by_hash:
            raise ValueError("Represent each distinct frame once in the workflow.")
        stage_name = stage.get("name", row["name"])
        if not isinstance(stage_name, str) or not stage_name.strip():
            raise ValueError("Give the stage a readable name.")
        parent_id = by_hash.get(stage.get("parent_sha256"))
        by_hash[row["sha256"]] = number
        current = images[number-1]
        parent = images[parent_id-1] if parent_id else original
        title = f"{stage_name} / {stage['tool']}"
        lines = [f"Reason: {stage['reason']}", f"Visual assessment: {decision['action']}."]
        if parameters:
            lines.append("Parameters: " + json.dumps(parameters, ensure_ascii=False, sort_keys=True))
        baseline = rows[parent_id-1] if parent_id else None
        if baseline:
            lines.append(f"Parent stage {parent_id}. Mean absolute luma error: "
                         f"{baseline['tone']['luma_mae']:.2f} to {row['tone']['luma_mae']:.2f}.")
        visual = decision_page(decision)
        pages.append({"title": title, "note": lines[0], "columns": ["Source", "Input frame", "Stage output"],
                      "rows": [[original, parent, current]], "lines": lines[1:] + row["findings"]})
        pages.append(dict(visual, title=f"{stage_name} / visual checks"))
        for check in decision["checks"]:
            name = check["region"]
            if name == "full":
                continue
            box = row["inspection_regions"][name]
            pages.append({"title": f"{stage_name} / {name}", "note": f"Source bounds {list(box)}.",
                          "columns": ["Source evidence", "Stage input", "Stage output"],
                          "rows": [[im.crop(native_box(im, original.size, box)) for im in (original, parent, current)]],
                          "lines": [check["source_evidence"], check["candidate_evidence"], check["next_action"]]})
        row["visual_review"] = decision["action"]
        trace.append(dict(decision, stage=number, name=stage_name, tool=stage["tool"], reason=stage["reason"],
                          parent_stage=parent_id, parameters=parameters))
    selected = by_hash.get(workflow.get("selected_sha256"))
    reason = workflow.get("selection_reason")
    if selected is None or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Identify the selected candidate and explain its selection.")
    state = trace[selected-1]["action"]
    comparison = None
    if "comparison_sha256" in workflow:
        comparison_hash = workflow["comparison_sha256"]
        comparison = by_hash.get(comparison_hash) if isinstance(comparison_hash, str) else None
        if comparison is None or comparison == selected:
            raise ValueError("Choose a distinct measured version for the comparison.")
    native = trace[selected-1].get("native_review")
    if final:
        repairs = []
        chosen = rows[selected-1]
        primary = chosen.get("primary_region")
        if primary and native and native["region"] != primary:
            repairs.append(f"Inspect the primary region {primary} at native size.")
        if any(a <= b for a, b in zip(chosen["size"], original.size)):
            repairs.append("Select an enlarged output for delivery.")
        for check in trace[selected-1]["checks"]:
            if check["status"] != "aligned":
                repairs.append(f"Revise {check['region']}: {check['next_action']}")
            elif not isinstance(check.get("residual_evidence"), str) or not check["residual_evidence"].strip():
                repairs.append(f"Record residual_evidence for {check['region']}.")
        if native is None:
            repairs.append("Compare the native crop with the enlarged source and record native_review.")
        elif native["status"] != "aligned":
            repairs.append(f"Revise {native['region']}: {native['next_action']}")
        if repairs:
            raise ValueError("Delivery actions:\n" + "\n".join(repairs))
    panel = {"title": "Selection and processing routes", "note": reason,
             "columns": ["Version", "Input", "Operation", "Assessment"],
             "rows": [[s["name"], trace[s["parent_stage"]-1]["name"] if s["parent_stage"] else "Source",
                       s["tool"], s["action"]] for s in trace],
             "lines": [f"Selected: {trace[selected-1]['name']}. Inspection outcome: {state}."]}
    return {"stages": trace, "selected_stage": selected, "selected_sha256": rows[selected-1]["sha256"],
            "selection_reason": reason, "comparison_stage": comparison, "final": final}, [panel, *pages]
