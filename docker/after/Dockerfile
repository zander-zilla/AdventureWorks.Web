# AFTER app: .NET 10, chiseled (distroless-style) non-root runtime. Build context: src/
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY global.json ./
COPY AdventureWorks.Web/AdventureWorks.Web.csproj AdventureWorks.Web/
RUN dotnet restore AdventureWorks.Web/AdventureWorks.Web.csproj
COPY AdventureWorks.Web/ AdventureWorks.Web/
RUN dotnet publish AdventureWorks.Web/AdventureWorks.Web.csproj -c Release -o /app --no-restore /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled-extra
WORKDIR /app
COPY --from=build /app ./
# chiseled images run as the non-root 'app' user (UID 1654) by default; make it explicit
USER $APP_UID
ENV ASPNETCORE_URLS=http://+:8080 ASPNETCORE_ENVIRONMENT=Production
EXPOSE 8080
ENTRYPOINT ["dotnet", "AdventureWorks.Web.dll"]
