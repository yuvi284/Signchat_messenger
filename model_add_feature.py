import torch
import torch.nn as nn


class TemporalAttentionPooling(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        mid_size = max(hidden_size // 2, 32)
        self.score = nn.Sequential(
            nn.Linear(hidden_size, mid_size),
            nn.Tanh(),
            nn.Linear(mid_size, 1),
        )

    def forward(self, x):
        weights = self.score(x).squeeze(-1)
        weights = torch.softmax(weights, dim=1).unsqueeze(-1)
        return torch.sum(x * weights, dim=1)


class SignLanguageLSTM(nn.Module):
    def __init__(self, input_size=648, hidden_size=192, num_layers=2, num_classes=10, dropout=0.35):
        super().__init__()

        self.input_proj = nn.Sequential(
            nn.LayerNorm(input_size),
            nn.Linear(input_size, hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
            bidirectional=True,
        )

        temporal_size = hidden_size * 2
        self.avg_pool_norm = nn.LayerNorm(temporal_size)
        self.attn_pool = TemporalAttentionPooling(temporal_size)
        self.attn_pool_norm = nn.LayerNorm(temporal_size)

        self.classifier = nn.Sequential(
            nn.Linear(temporal_size * 2, temporal_size),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(temporal_size, num_classes),
        )

    def forward(self, x):
        x = self.input_proj(x)
        lstm_out, _ = self.lstm(x)

        avg_out = self.avg_pool_norm(torch.mean(lstm_out, dim=1))
        attn_out = self.attn_pool_norm(self.attn_pool(lstm_out))
        pooled = torch.cat([avg_out, attn_out], dim=1)

        return self.classifier(pooled)
