FROM apache/airflow:3.3.1

USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Taipei

# 直接寫死一份新的來源設定，明確分開一般套件庫（用台灣鏡像）跟security（維持官方源）
RUN echo "deb http://ftp.tw.debian.org/debian bookworm main" > /etc/apt/sources.list.d/debian.list \
    && echo "deb http://ftp.tw.debian.org/debian bookworm-updates main" >> /etc/apt/sources.list.d/debian.list \
    && echo "deb http://deb.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list.d/debian.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt