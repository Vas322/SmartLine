"""Instruction management and schedule mirror views."""
import logging

from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.decorators import member_required, staff_or_404
from core.forms import InstructionForm
from core.models import Instruction, ScheduleMirror
from core.services import schedule_mirror_service


logger = logging.getLogger(__name__)


def _unique_instruction_slug(base: str) -> str:
    """Return a slug that does not collide with existing Instruction slugs."""
    from django.utils.text import slugify

    slug = slugify(base) or "instruction"
    original = slug
    n = 2
    while Instruction.objects.filter(slug=slug).exists():
        slug = f"{original}-{n}"
        n += 1
    return slug


@member_required
def instructions(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("add", "delete") and not request.user.is_staff:
            return HttpResponseForbidden("Недостаточно прав для управления инструкциями.")
        if action == "add":
            slug = _unique_instruction_slug("instruction")
            instr = None
            for _ in range(5):
                try:
                    instr = Instruction.objects.create(title="Новая инструкция", slug=slug)
                    break
                except IntegrityError:
                    slug = _unique_instruction_slug("instruction")
            if instr is None:
                return redirect("instructions")
            return redirect("instruction_edit", pk=instr.pk)
        if action == "delete":
            pk = request.POST.get("pk")
            Instruction.objects.filter(pk=pk).delete()
            return redirect("instructions")
    instructions_qs = Instruction.objects.order_by("title")
    return render(
        request,
        "core/instructions.html",
        {"instructions": instructions_qs, "saved": request.GET.get("saved")},
    )


@member_required
def instruction_detail(request, pk: int):
    instr = get_object_or_404(Instruction, pk=pk)
    return render(
        request,
        "core/instruction_detail.html",
        {"instruction": instr},
    )


@staff_or_404
def instruction_edit(request, pk: int):
    instr = get_object_or_404(Instruction, pk=pk)
    if request.method == "POST":
        form = InstructionForm(request.POST, instance=instr)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.updated_by = request.user
            saved.save()
            return redirect(reverse("instructions") + "?saved=1")
    else:
        form = InstructionForm(instance=instr)
    return render(
        request,
        "core/instruction_edit.html",
        {"form": form, "instruction": instr},
    )


@member_required
def schedule_mirror(request):
    """Manage schedule mirroring from alliance bot to clan group."""
    current_mirror = ScheduleMirror.objects.filter(is_active=True).first()
    current_text = schedule_mirror_service.get_current_text()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reconcile":
            if not request.user.is_staff:
                return HttpResponseForbidden("Только для персонала.")
            schedule_mirror_service.reconcile_all()
            messages.success(request, "Синхронизация выполнена.")
            return redirect("schedule_mirror")

    context = {
        "current_mirror": current_mirror,
        "current_text": current_text,
    }
    return render(request, "core/schedule_mirror.html", context)