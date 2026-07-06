"""
微调训练入口模块
整合 dataset_manager（数据管理）和 LLaMA Factory（训练引擎）
支持通过 Python API 或命令行启动训练
"""
from __future__ import annotations


import sys
import os
from pathlib import Path
from typing import Optional, Any

# 确保本地 llamafactory 包能被导入
sys.path.insert(0, str(Path(__file__).parent))

from dataset_manager import DatasetManager, DataFormat, DatasetMetadata


class FinetuneRunner:
    """
    微调训练运行器 —— 一站式微调入口

    使用方式：
        # 方式1: 用 YAML 配置文件启动训练
        runner = FinetuneRunner()
        runner.train_from_yaml("examples/train_lora/llama3_lora_sft.yaml")

        # 方式2: 用 Python 字典参数启动训练
        runner.train_from_dict({
            "model_name_or_path": "meta-llama/Llama-3-8B",
            "stage": "sft",
            "do_train": True,
            "finetuning_type": "lora",
            "dataset": "my_dataset",
            "template": "llama3",
            "output_dir": "output/llama3_lora",
            "per_device_train_batch_size": 2,
            "gradient_accumulation_steps": 4,
            "lr_scheduler_type": "cosine",
            "logging_steps": 10,
            "save_steps": 500,
            "learning_rate": 5e-5,
            "num_train_epochs": 3.0,
            "lora_rank": 8,
            "lora_target": "all",
            "overwrite_output_dir": True,
        })

        # 方式3: 命令行方式
        #   python run_finetune.py --config examples/train_lora/llama3_lora_sft.yaml
        #   python run_finetune.py --model_name_or_path Qwen/Qwen2-7B --stage sft ...

    数据准备：
        # 先用 dataset_manager 上传和校验数据
        mgr = DatasetManager()
        metadata = DatasetMetadata(
            name="train_data",
            required_fields=["instruction", "output"]
        )
        mgr.upload(file_path="my_data.jsonl", dataset_name="my_dataset",
                   format=DataFormat.JSONL, metadata=metadata)
        # 然后在 dataset_info.json 中注册该数据集
    """

    def __init__(self):
        self._dataset_manager = DatasetManager()

    @property
    def dataset_manager(self) -> DatasetManager:
        """获取数据集管理器实例"""
        return self._dataset_manager

    def prepare_dataset(
        self,
        file_path: str,
        dataset_name: str,
        required_fields: Optional[list[str]] = None,
        format_type: str = "jsonl",
        description: str = "",
    ) -> tuple[bool, str]:
        """
        准备数据集：校验并注册到本地存储

        Args:
            file_path: 数据文件路径
            dataset_name: 数据集名称（需与 dataset_info.json 中注册的名称一致）
            required_fields: 必填字段列表，如 ["instruction", "output"]
            format_type: 数据格式 "json" 或 "jsonl"
            description: 数据集描述

        Returns:
            (success, message)
        """
        fmt = DataFormat.JSONL if format_type == "jsonl" else DataFormat.JSON

        metadata = DatasetMetadata(
            name=dataset_name,
            description=description,
            required_fields=required_fields or [],
        )

        success, msg, version, results = self._dataset_manager.upload(
            file_path=file_path,
            dataset_name=dataset_name,
            format=fmt,
            metadata=metadata,
            description=description,
        )

        if results:
            print("\n--- 校验结果 ---")
            for r in results:
                tag = "[阻断]" if r.level == "blocking" else "[警告]"
                print(f"  {tag} {r.code}: {r.message}")

        if version:
            print(f"\n版本创建成功: {version.version_id}")
            print(f"数据行数: {version.row_count}")
            print(f"检测字段: {', '.join(version.fields)}")

        return success, msg

    def list_datasets(self) -> list[str]:
        """列出所有已注册的数据集"""
        return self._dataset_manager.list_datasets()

    def train_from_yaml(self, config_path: str, **overrides) -> None:
        """
        使用 YAML 配置文件启动训练

        Args:
            config_path: YAML 配置文件路径
            **overrides: 额外的命令行参数覆盖
        """
        from llamafactory.train.tuner import run_exp

        args = [config_path]
        for key, value in overrides.items():
            args.append(f"--{key}")
            args.append(str(value))

        print(f"[FinetuneRunner] 启动训练，配置: {config_path}")
        run_exp(args)

    def train_from_dict(self, config: dict[str, Any]) -> None:
        """
        使用 Python 字典参数启动训练

        Args:
            config: 训练参数字典
        """
        from llamafactory.train.tuner import run_exp

        args = []
        for key, value in config.items():
            args.append(f"--{key}")
            args.append(str(value))

        print(f"[FinetuneRunner] 启动训练，参数数量: {len(config)}")
        run_exp(args)

    def export_model(
        self,
        model_name_or_path: str,
        adapter_name_or_path: str,
        export_dir: str,
        template: str = "default",
        export_size: int = 5,
    ) -> None:
        """
        导出/合并 LoRA 模型权重

        Args:
            model_name_or_path: 基座模型路径
            adapter_name_or_path: LoRA adapter 路径
            export_dir: 导出目录
            template: 对话模板名称
            export_size: 分片大小 (GB)
        """
        from llamafactory.train.tuner import export_model

        args = [
            "--model_name_or_path", model_name_or_path,
            "--adapter_name_or_path", adapter_name_or_path,
            "--template", template,
            "--export_dir", export_dir,
            "--export_size", str(export_size),
        ]
        export_model(args)


# ============================================================
# 命令行入口
# ============================================================
def main():
    """
    命令行入口，支持三种模式：

    1. 训练模式（默认）:
       python run_finetune.py --config <yaml_path>
       python run_finetune.py --model_name_or_path xxx --stage sft --dataset my_data ...

    2. 导出模式:
       python run_finetune.py export --model_name_or_path xxx --adapter_name_or_path xxx --export_dir output/

    3. 数据准备模式:
       python run_finetune.py prepare --file data.jsonl --name my_dataset --fields instruction,output
    """
    import argparse

    parser = argparse.ArgumentParser(description="LLaMA Factory 微调训练入口")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ---- 训练子命令 ----
    train_parser = subparsers.add_parser("train", help="启动微调训练")
    train_parser.add_argument("--config", type=str, default=None, help="YAML 配置文件路径")
    train_parser.add_argument("extra", nargs="*", help="额外参数 (--key value 格式)")

    # ---- 导出子命令 ----
    export_parser = subparsers.add_parser("export", help="导出/合并模型")
    export_parser.add_argument("--model_name_or_path", type=str, required=True)
    export_parser.add_argument("--adapter_name_or_path", type=str, required=True)
    export_parser.add_argument("--export_dir", type=str, required=True)
    export_parser.add_argument("--template", type=str, default="default")
    export_parser.add_argument("--export_size", type=int, default=5)

    # ---- 数据准备子命令 ----
    prepare_parser = subparsers.add_parser("prepare", help="准备/校验数据集")
    prepare_parser.add_argument("--file", type=str, required=True, help="数据文件路径")
    prepare_parser.add_argument("--name", type=str, required=True, help="数据集名称")
    prepare_parser.add_argument("--fields", type=str, default="", help="必填字段，逗号分隔")
    prepare_parser.add_argument("--format", type=str, default="jsonl", choices=["json", "jsonl"])
    prepare_parser.add_argument("--desc", type=str, default="", help="数据集描述")

    # 如果没有子命令，直接用 --help 接入 LLaMA Factory 的 argparser
    known_args, unknown_args = parser.parse_known_args()

    runner = FinetuneRunner()

    if known_args.command == "export":
        runner.export_model(
            model_name_or_path=known_args.model_name_or_path,
            adapter_name_or_path=known_args.adapter_name_or_path,
            export_dir=known_args.export_dir,
            template=known_args.template,
            export_size=known_args.export_size,
        )

    elif known_args.command == "prepare":
        fields = [f.strip() for f in known_args.fields.split(",") if f.strip()]
        success, msg = runner.prepare_dataset(
            file_path=known_args.file,
            dataset_name=known_args.name,
            required_fields=fields or None,
            format_type=known_args.format,
            description=known_args.desc,
        )
        print(f"\n结果: {msg}")
        if not success:
            sys.exit(1)

    elif known_args.command == "train":
        if known_args.config:
            runner.train_from_yaml(known_args.config)
        else:
            # 从 extra 参数构建 dict
            config_dict = {}
            extra = known_args.extra
            i = 0
            while i < len(extra):
                key = extra[i].lstrip("-")
                if i + 1 < len(extra) and not extra[i + 1].startswith("-"):
                    config_dict[key] = extra[i + 1]
                    i += 2
                else:
                    config_dict[key] = "True"
                    i += 1
            if config_dict:
                runner.train_from_dict(config_dict)
            else:
                train_parser.print_help()

    else:
        # 默认：将全部参数透传给 LLaMA Factory 的 argparser
        from llamafactory.train.tuner import run_exp
        run_exp(sys.argv[1:])


if __name__ == "__main__":
    main()
