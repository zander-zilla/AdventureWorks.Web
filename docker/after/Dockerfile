# AFTER app: .NET 10, chiseled (distroless-style) non-root runtime. Build context: src/
# Chapter 2 (ADR 0010): the React SPA (src/web) is built here and served by the app under /app/.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# C2-1: the chapter switch's "Chapter 1" goes to <showcase>/c1/ (Terraform output showcase_url, set by push-images.sh)
ARG VITE_SHOWCASE_URL=""
ENV VITE_SHOWCASE_URL=$VITE_SHOWCASE_URL
RUN npm run build

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY global.json ./
COPY AdventureWorks.Web/AdventureWorks.Web.csproj AdventureWorks.Web/
RUN dotnet restore AdventureWorks.Web/AdventureWorks.Web.csproj
COPY AdventureWorks.Web/ AdventureWorks.Web/
RUN dotnet publish AdventureWorks.Web/AdventureWorks.Web.csproj -c Release -o /app --no-restore /p:UseAppHost=false
COPY --from=web /web/dist /app/wwwroot/app

FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled-extra
WORKDIR /app
COPY --from=build /app ./
# chiseled images run as the non-root 'app' user (UID 1654) by default; make it explicit
USER $APP_UID
ENV ASPNETCORE_URLS=http://+:8080 ASPNETCORE_ENVIRONMENT=Production
EXPOSE 8080
ENTRYPOINT ["dotnet", "AdventureWorks.Web.dll"]
