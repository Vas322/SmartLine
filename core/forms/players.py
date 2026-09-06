"""Player forms."""
import re

from django import forms

from core.models import Player


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["nickname"]
        widgets = {
            "nickname": forms.TextInput(attrs={"placeholder": "Игровой ник"}),
        }

    def clean_nickname(self) -> str:
        nickname = self.cleaned_data["nickname"].strip()
        if Player.objects.filter(nickname__iexact=nickname).exists():
            raise forms.ValidationError(
                f"Игрок с ником «{nickname}» уже существует (регистр не важен)."
            )
        if not re.fullmatch(r"^[A-Za-zА-Яа-яЁё0-9]+$", nickname):
            raise forms.ValidationError(
                "Ник может содержать только буквы русского/английского алфавита и цифры. Пожалуйста, исправьте игровой ник на корректный."
            )
        return nickname


class PlayerEditForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["nickname", "telegram_user_id"]
        widgets = {
            "nickname": forms.TextInput(attrs={"placeholder": "Игровой ник"}),
            "telegram_user_id": forms.NumberInput(
                attrs={"placeholder": "Telegram user ID (необязательно)"}
            ),
        }
        labels = {
            "nickname": "Ник",
            "telegram_user_id": "Telegram user ID",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["telegram_user_id"].required = False

    def clean_nickname(self) -> str:
        nickname = self.cleaned_data["nickname"].strip()
        if not re.fullmatch(r"^[A-Za-zА-Яа-яЁё0-9]+$", nickname):
            raise forms.ValidationError(
                "Ник может содержать только буквы русского/английского алфавита и цифры. Пожалуйста, исправьте игровой ник на корректный."
            )
        existing = (
            Player.objects.filter(nickname__iexact=nickname)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if existing:
            raise forms.ValidationError(
                f"Игрок с ником «{nickname}» уже существует (регистр не важен)."
            )
        return nickname

    def clean_telegram_user_id(self):
        user_id = self.cleaned_data.get("telegram_user_id")
        if user_id is None:
            return None
        existing = (
            Player.objects.filter(telegram_user_id=user_id)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if existing:
            raise forms.ValidationError(
                "Этот Telegram user ID уже привязан к другому игроку."
            )
        return user_id
