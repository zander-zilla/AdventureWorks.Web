# Original app on its original runtime (netcoreapp2.1, EOL) - before baseline only.
FROM mcr.microsoft.com/dotnet/core/sdk:2.1 AS build
WORKDIR /src
COPY AdventureWorks.Web.csproj global.json ./
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /out
FROM mcr.microsoft.com/dotnet/core/aspnet:2.1
WORKDIR /app
COPY --from=build /out .
ENTRYPOINT ["dotnet", "AdventureWorks.Web.dll"]
